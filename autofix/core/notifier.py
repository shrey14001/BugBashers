"""
core/notifier.py
Sends email alerts for known errors (errors that match a past fix in ChromaDB).

Configure via environment variables:
  SMTP_HOST      — SMTP server hostname  (default: localhost)
  SMTP_PORT      — SMTP port             (default: 587)
  SMTP_USER      — SMTP username / sender address
  SMTP_PASSWORD  — SMTP password
  NOTIFY_EMAIL   — recipient address for alerts
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST    = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")


def send_known_error_email(
    error_message: str,
    commit_id: str,
    pr_url: str | None,
    similarity_score: float,
    domain: str | None,
) -> None:
    """
    Send an alert email when a known error is detected.
    Logs a warning and returns silently if SMTP is not configured.
    """
    if not NOTIFY_EMAIL or not SMTP_USER:
        print(
            f"[Notifier] SMTP not configured — skipping email.\n"
            f"           Error   : {error_message[:120]}\n"
            f"           Commit  : {commit_id}\n"
            f"           PR      : {pr_url}\n"
            f"           Score   : {similarity_score:.4f}\n"
            f"           Domain  : {domain}"
        )
        return

    subject = f"[AutoFix] Known error detected on {domain or 'unknown domain'}"
    body = f"""\
A production error has been detected that matches a previously fixed issue.

Error:
  {error_message}

Domain:   {domain or 'N/A'}
Similarity score: {similarity_score:.4f}

Previous fix:
  Commit : {commit_id}
  PR     : {pr_url or 'N/A'}

No new PR was created — the previous fix should resolve this.
Please verify it has been deployed.
"""

    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            if SMTP_PORT != 25:
                server.starttls()
            if SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())
        print(f"[Notifier] Alert email sent to {NOTIFY_EMAIL}.")
    except Exception as e:
        print(f"[Notifier] Failed to send email: {e}")
