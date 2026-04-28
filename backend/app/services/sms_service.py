"""
sms_service.py — wysyłanie SMS przez USB modem SIM800C (komendy AT via pyserial).

Konfiguracja w backend/.env:
  SMS_ENABLED=true
  SMS_SERIAL_PORT=/dev/ttyUSB0      # sprawdź: ls /dev/ttyUSB* lub dmesg | grep tty
  SMS_BAUD_RATE=9600
  SMS_RECIPIENT_PHONE=+48XXXXXXXXX  # numer odbiorcy w formacie E.164

Wymagane: pip install pyserial
Uprawnienia do portu: sudo usermod -a -G dialout $USER  (lub: chmod 666 /dev/ttyUSB0)
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.core.config import settings

_lock = threading.Lock()
_MAX_SMS_LEN = 160


def _at(ser, cmd: str, wait: float = 0.5) -> bytes:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    return ser.read_all()


def send_sms(message: str, phone: Optional[str] = None) -> bool:
    """
    Wysyła SMS przez SIM800C. Zwraca True jeśli +CMGS pojawi się w odpowiedzi.
    Wiadomość jest przycinana do 160 znaków.
    Blokuje port przez czas wysyłania (~4 s).
    """
    if not settings.sms_enabled:
        return False

    recipient = phone or settings.sms_recipient_phone
    if not recipient:
        print("[sms] brak SMS_RECIPIENT_PHONE w .env — pomijam")
        return False

    text = message[:_MAX_SMS_LEN]

    with _lock:
        try:
            import serial  # pyserial
        except ImportError:
            print("[sms] pyserial nie zainstalowane — pip install pyserial")
            return False

        try:
            with serial.Serial(
                settings.sms_serial_port,
                baudrate=settings.sms_baud_rate,
                timeout=5,
            ) as ser:
                ser.flushInput()

                # Sprawdź połączenie z modemem
                resp = _at(ser, "AT")
                if b"OK" not in resp:
                    print(f"[sms] modem nie odpowiada na AT: {resp!r}")
                    return False

                # Tryb tekstowy
                _at(ser, "AT+CMGF=1")

                # Inicjuj wysyłkę
                _at(ser, f'AT+CMGS="{recipient}"', wait=1.0)

                # Treść + Ctrl+Z (0x1a) = wyślij
                ser.write(f"{text}\x1a".encode("utf-8", errors="replace"))
                time.sleep(4)  # SIM800C potrzebuje ~2-4 s na wysyłkę

                response = ser.read_all()
                ok = b"+CMGS" in response
                if ok:
                    print(f"[sms] ✓ Wysłano SMS na {recipient}: {text[:40]}…")
                else:
                    print(f"[sms] ✗ Błąd wysyłki — odpowiedź: {response!r}")
                return ok

        except Exception as exc:
            print(f"[sms] BŁĄD portu szeregowego ({settings.sms_serial_port}): {exc}")
            return False


def test_sms() -> bool:
    """Wysyła testowy SMS. Możesz wywołać z endpointu admin."""
    return send_sms("MStock: Test SMS. Jeśli widzisz tę wiadomość, SIM800C działa poprawnie.")
