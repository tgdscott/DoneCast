from __future__ import annotations

import os
import smtplib
import socket
from email.message import EmailMessage
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Mailer:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        # Support both SMTP_PASS (documented) and legacy/alternate SMTP_PASSWORD
        self.password = os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD")
        if not os.getenv("SMTP_PASS") and os.getenv("SMTP_PASSWORD") and not self.password:
            logger.warning("SMTP_PASSWORD is set but SMTP_PASS not found and password resolution failed")
        if os.getenv("SMTP_PASSWORD") and not os.getenv("SMTP_PASS"):
            logger.info("Using SMTP_PASSWORD fallback for mailer secret")
        # Rebrand default sender domain (retain old via SMTP_FROM override if needed)
        self.sender = os.getenv("SMTP_FROM", "no-reply@podcastplusplus.com")
        self.sender_name = os.getenv("SMTP_FROM_NAME", "Podcast Plus Plus")

        # Perform a lightweight startup probe so deploys fail fast when DNS or
        # networking is misconfigured. We only warn instead of raising because
        # the service should keep running (operators can still fix the env vars
        # live without a redeploy).
        self._startup_probe()

    def _startup_probe(self) -> None:
        """Validate that the configured SMTP host resolves and is reachable."""

        if not self.host:
            logger.info("SMTP_HOST not configured; mailer will log emails to stdout")
            return

        try:
            info = socket.getaddrinfo(self.host, self.port)
        except socket.gaierror as dns_err:
            logger.error("Unable to resolve SMTP host '%s': %s", self.host, dns_err)
            return

        # Collapse results into a distinct set of IP addresses for logging.
        addresses = sorted({result[4][0] for result in info if result[4]})
        if addresses:
            logger.info("SMTP host '%s' resolved to %s", self.host, ", ".join(addresses))

        try:
            with socket.create_connection((self.host, self.port), timeout=5):
                logger.info("SMTP connectivity probe succeeded to %s:%s", self.host, self.port)
        except OSError as conn_err:
            logger.warning(
                "SMTP connectivity probe failed to %s:%s: %s. Check outbound firewall rules.",
                self.host,
                self.port,
                conn_err,
            )

    def send(self, to: str, subject: str, text: str, html: Optional[str] = None) -> bool:
        """Send an email. Returns True if accepted by remote SMTP server.

        Adds richer diagnostics so operators can debug common deployment issues
        (auth failures, relay denial, missing env vars) without needing to
        reproduce locally.
        """
        if not self.host:
            # Dev fallback: log to stdout so tests and dev still see the code
            print(f"[DEV-MAIL] To: {to}\nSubject: {subject}\n\n{text}")
            return True

        msg = EmailMessage()
        if self.sender_name and '<' not in self.sender:
            msg["From"] = f"{self.sender_name} <{self.sender}>"
        else:
            msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        # Proactive sanity checks
        if not (self.user and self.password):
            logger.warning(
                "SMTP credentials not fully configured (user=%s, pass_present=%s); attempting unauthenticated send which many providers disallow.",
                bool(self.user), bool(self.password)
            )
        if "@" not in self.sender:
            logger.warning("Configured SMTP_FROM '%s' lacks '@'; this may be rejected by provider", self.sender)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                # Identify ourselves & upgrade to TLS
                server.ehlo()
                try:
                    server.starttls()
                    server.ehlo()
                except smtplib.SMTPException as tls_err:
                    logger.warning("SMTP STARTTLS failed (%s); continuing without TLS", tls_err)

                if self.user and self.password:
                    try:
                        server.login(self.user, self.password)
                    except smtplib.SMTPAuthenticationError as auth_err:
                        logger.error("SMTP auth failed: code=%s msg=%s", getattr(auth_err, 'smtp_code', '?'), getattr(auth_err, 'smtp_error', auth_err))
                        raise

                # Send
                server.send_message(msg)
                logger.info(
                    "SMTP mail accepted: to=%s from=%s host=%s:%s user_set=%s", to, self.sender, self.host, self.port, bool(self.user)
                )
            return True
        except smtplib.SMTPRecipientsRefused as refused:
            detail = {}
            for rcpt, (code, errmsg) in refused.recipients.items():  # type: ignore[attr-defined]
                detail[rcpt] = {"code": code, "error": (errmsg.decode() if isinstance(errmsg, bytes) else str(errmsg))}
            logger.error("SMTPRecipientsRefused: %s", detail)
            # Helpful hint for common 550 relay denial
            if any(v.get("code") == 550 for v in detail.values()):
                logger.error(
                    "Relay denied (550). Likely causes: (1) wrong SMTP_HOST for region, (2) missing/invalid SMTP_USER+SMTP_PASS, (3) FROM domain '%s' not authorized (SPF/DKIM), (4) attempting to send before domain verification.",
                    self.sender,
                )
            print(f"[MAIL-ERROR] {detail}")
            return False
        except (smtplib.SMTPException, OSError, socket.timeout) as e:
            logger.exception("General SMTP failure sending to %s: %s", to, e)
            print(f"[MAIL-ERROR] {e}")
            return False

mailer = Mailer()
