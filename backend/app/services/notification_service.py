from __future__ import annotations

import base64
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.notifications import create_notification_event, get_notification_channel


def send_email_notification(db: Session, channel_id: int, subject: str, message: str, asset_id: str | None = None) -> dict:
    channel = get_notification_channel(db, channel_id)
    if channel is None:
        raise ValueError("Unknown channel")

    if not settings.smtp_host or not settings.smtp_from_email:
        create_notification_event(db, channel_id, asset_id, "email", "error", "SMTP not configured")
        db.commit()
        return {"sent": False, "detail": "SMTP not configured"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = channel.target
    msg.set_content(message)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        create_notification_event(db, channel_id, asset_id, "email", "sent", message)
        db.commit()
        return {"sent": True}
    except Exception as exc:
        create_notification_event(db, channel_id, asset_id, "email", "error", str(exc))
        db.commit()
        return {"sent": False, "detail": str(exc)}


def send_whatsapp_notification(db: Session, channel_id: int, message: str, asset_id: str | None = None) -> dict:
    channel = get_notification_channel(db, channel_id)
    if channel is None:
        raise ValueError("Unknown channel")

    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_whatsapp_from:
        create_notification_event(db, channel_id, asset_id, "whatsapp", "error", "Twilio WhatsApp not configured")
        db.commit()
        return {"sent": False, "detail": "Twilio WhatsApp not configured"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    data = {
        "From": settings.twilio_whatsapp_from,
        "To": channel.target,
        "Body": message,
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, data=data, auth=auth)
            response.raise_for_status()
        create_notification_event(db, channel_id, asset_id, "whatsapp", "sent", message)
        db.commit()
        return {"sent": True}
    except Exception as exc:
        create_notification_event(db, channel_id, asset_id, "whatsapp", "error", str(exc))
        db.commit()
        return {"sent": False, "detail": str(exc)}
