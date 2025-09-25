from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Optional


class Mailer:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASS")
        self.sender = os.getenv("SMTP_FROM", "no-reply@getpodcastplus.com")

    def send(self, to: str, subject: str, text: str, html: Optional[str] = None) -> bool:
        if not self.host:
            # Dev fallback: log to stdout so tests and dev still see the code
            print(f"[DEV-MAIL] To: {to}\nSubject: {subject}\n\n{text}")
            return True
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[MAIL-ERROR] {e}")
            return False

mailer = Mailer()
