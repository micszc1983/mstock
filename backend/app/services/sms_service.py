"""
sms_service.py — wysyłanie i odbieranie SMS przez USB modem SIM800C (komendy AT via pyserial).

Konfiguracja w backend/.env:
  SMS_ENABLED=true
  SMS_SERIAL_PORT=/dev/ttyUSB0      # sprawdź: ls /dev/ttyUSB* lub dmesg | grep tty
  SMS_BAUD_RATE=9600
  SMS_RECIPIENT_PHONE=+48XXXXXXXXX  # numer odbiorcy w formacie E.164

Wymagane: pip install pyserial
Uprawnienia do portu: sudo usermod -a -G dialout $USER  (lub: chmod 666 /dev/ttyUSB0)

Obsługiwane komendy SMS (treść wiadomości, wielkość liter bez znaczenia):
  "raport"  — wysyła aktualny raport portfela na maila
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings

_lock = threading.Lock()
_MAX_SMS_LEN = 160


def _at(ser, cmd: str, wait: float = 0.5) -> bytes:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    return ser.read_all()


# ── Wysyłanie ─────────────────────────────────────────────────────────────────

def send_sms(message: str, phone: Optional[str] = None) -> bool:
    """
    Wysyła SMS przez SIM800C. Zwraca True jeśli +CMGS pojawi się w odpowiedzi.
    Wiadomość jest przycinana do 160 znaków. Blokuje port przez ~4 s.
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

                resp = _at(ser, "AT")
                if b"OK" not in resp:
                    print(f"[sms] modem nie odpowiada na AT: {resp!r}")
                    return False

                _at(ser, "AT+CMGF=1")
                _at(ser, f'AT+CMGS="{recipient}"', wait=1.0)

                ser.write(f"{text}\x1a".encode("utf-8", errors="replace"))
                time.sleep(4)

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
    return send_sms("MStock: Test SMS. Jesli widzisz te wiadomosc, SIM800C dziala poprawnie.")


# ── Odbieranie ────────────────────────────────────────────────────────────────

@dataclass
class IncomingSms:
    index: int        # indeks slotu w pamięci modemu
    sender: str       # numer nadawcy
    timestamp: str    # timestamp z modemu (może być pusty)
    text: str         # treść wiadomości


def _decode_sms_body(body: str) -> str:
    """
    Dekoduje treść SMS. SIM800C może zwrócić tekst jako hex UCS-2 (UTF-16 BE)
    gdy telefon nadawcy użył kodowania Unicode (np. polskie znaki lub emoji).
    Przykład: '005200610070006F00720074' → 'Raport'
    """
    stripped = body.strip()
    # Heurystyka: same znaki hex i parzysta długość podzielna przez 4
    if (
        len(stripped) >= 4
        and len(stripped) % 4 == 0
        and all(c in "0123456789abcdefABCDEF" for c in stripped)
    ):
        try:
            return bytes.fromhex(stripped).decode("utf-16-be")
        except Exception:
            pass
    return stripped


def _parse_cmgl(raw: bytes) -> list[IncomingSms]:
    """
    Parsuje odpowiedź AT+CMGL="ALL" w trybie tekstowym.

    Format odpowiedzi SIM800C:
      +CMGL: <index>,"<status>","<sender>","","<timestamp>"
      <treść>
    """
    messages: list[IncomingSms] = []
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return messages

    # Każdy SMS zaczyna się od "+CMGL: "
    pattern = re.compile(
        r'\+CMGL:\s*(\d+),"[^"]*","([^"]*)",[^,]*,"([^"]*)"[^\n]*\n([^\n+]*)',
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        index     = int(m.group(1))
        sender    = m.group(2).strip()
        timestamp = m.group(3).strip()
        body      = _decode_sms_body(m.group(4))
        if body:
            messages.append(IncomingSms(index=index, sender=sender, timestamp=timestamp, text=body))
    return messages


def read_and_clear_sms() -> list[IncomingSms]:
    """
    Odczytuje wszystkie SMS z pamięci SIM800C i usuwa je po odczycie.
    Blokuje port przez ~3 s. Zwraca pustą listę gdy SMS_ENABLED=false lub błąd.
    """
    if not settings.sms_enabled:
        return []

    with _lock:
        try:
            import serial  # pyserial
        except ImportError:
            return []

        try:
            with serial.Serial(
                settings.sms_serial_port,
                baudrate=settings.sms_baud_rate,
                timeout=5,
            ) as ser:
                ser.flushInput()

                resp = _at(ser, "AT")
                if b"OK" not in resp:
                    print(f"[sms] modem nie odpowiada przy odczycie: {resp!r}")
                    return []

                # Tryb tekstowy
                _at(ser, "AT+CMGF=1")

                # Wymuś przechowywanie przychodzących SMS w pamięci modemu (ME),
                # nie routing bezpośrednio na port — to jest domyślny problem SIM800C
                _at(ser, 'AT+CPMS="ME","ME","ME"')
                # CNMI=2,1: zapisuj SMS do pamięci i wysyłaj +CMTI, nie drukuj od razu
                _at(ser, "AT+CNMI=2,1,0,0,0")

                # Odczytaj wszystkie SMS z obu pamięci (SM = SIM, ME = modem)
                raw_me = _at(ser, 'AT+CMGL="ALL"', wait=1.5)
                _at(ser, 'AT+CPMS="SM","SM","SM"')
                raw_sm = _at(ser, 'AT+CMGL="ALL"', wait=1.5)

                messages = _parse_cmgl(raw_me) + _parse_cmgl(raw_sm)

                if messages:
                    # Usuń wszystkie wiadomości z obu pamięci
                    _at(ser, 'AT+CPMS="ME","ME","ME"')
                    _at(ser, "AT+CMGD=1,4", wait=1.0)
                    _at(ser, 'AT+CPMS="SM","SM","SM"')
                    _at(ser, "AT+CMGD=1,4", wait=1.0)
                    print(f"[sms] Odczytano {len(messages)} SMS, skasowano z pamięci modemu")

                return messages

        except Exception as exc:
            print(f"[sms] BŁĄD odczytu SMS ({settings.sms_serial_port}): {exc}")
            return []