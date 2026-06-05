"""
core/notifier.py
Sends email alerts via Bizom's internal notification service.

Environment variables:
  NOTIFICATION_URL       — e.g. http://notification-producer.staging:8080/notification/
  NOTIFICATION_EMAIL_TO  — JSON array string, e.g. ["divita.jain@mobisy.com"]
  NOTIFICATION_COMPANY_ID — company ID passed to the notification service (default: 1)
"""

import os
import json
import logging
import requests
from requests_toolbelt import MultipartEncoder
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

NOTIFICATION_URL        = os.getenv("NOTIFICATION_URL", "")
NOTIFICATION_EMAIL_TO   = os.getenv("NOTIFICATION_EMAIL_TO", "[]")
NOTIFICATION_COMPANY_ID = int(os.getenv("NOTIFICATION_COMPANY_ID", "1"))


def _post_notification_email(message: str, subject: str, company_id: int) -> None:
    """
    Send an HTML email via the internal notification service.
    Logs and returns silently on any failure so it never blocks the pipeline.
    """
    if not NOTIFICATION_URL:
        logger.warning("[Notifier] NOTIFICATION_URL not set — skipping email.")
        print(f"[Notifier] NOTIFICATION_URL not set — skipping email.\n"
              f"           Subject : {subject}\n"
              f"           Body    : {message[:200]}")
        return

    payload = {
        "companyId": str(company_id),
        "userId": "1",
        "channel": "email",
        "priority": "low",
        "client": "autofix-agent",
        "vendor": "aws",
        "channelData": {
            "messageType": "company-info",
            "subject": subject,
            "to": json.loads(NOTIFICATION_EMAIL_TO),
            "body": message,
        },
    }

    try:
        notification_data = json.dumps(payload)
        multipart_data = MultipartEncoder(
            fields={"notificationEmailInput": notification_data}
        )
        headers = {"Content-Type": multipart_data.content_type}
        logger.info(
            f"[Notifier] POST to {NOTIFICATION_URL} | company_id={company_id} "
            f"| to={NOTIFICATION_EMAIL_TO}"
        )
        response = requests.post(
            NOTIFICATION_URL, data=multipart_data, headers=headers, timeout=30
        )
        logger.info(
            f"[Notifier] Response status={response.status_code} | "
            f"body={response.text[:300]}"
        )
        response.raise_for_status()
        print(f"[Notifier] Alert email sent successfully.")
    except Exception as e:
        print(f"[Notifier] Failed to send email: {e}")


def _build_known_error_html(
    error_message: str,
    commit_id: str,
    pr_url: str | None,
    similarity_score: float,
    domain: str | None,
    forward_ported: bool = False,
) -> str:
    pr_link = (
        f'<a href="{pr_url}" style="color:#2563eb">{pr_url}</a>'
        if pr_url else "N/A"
    )

    if forward_ported:
        badge         = '<span class="badge" style="background:#d1fae5;color:#065f46;">🔀 Forward-Ported</span>'
        pr_label      = "Forward-Port PR (NEW — please review &amp; merge)"
        action_banner = f"""
    <div class="section" style="background:#eff6ff; border-radius:6px; padding:14px 16px; margin-top:24px;">
      <strong>✅ A forward-port PR has been created for <em>{domain or "the affected domain"}</em>.</strong><br>
      The fix from the original commit below has been re-applied onto the current deployment tag.<br>
      <strong>Please review and merge the PR above to resolve this error.</strong>
    </div>"""
    else:
        badge         = '<span class="badge">⚠️ Already Fixed</span>'
        pr_label      = "Previous Fix — Pull Request"
        action_banner = f"""
    <div class="section" style="background:#ecfdf5; border-radius:6px; padding:14px 16px; margin-top:24px;">
      <strong>ℹ️ No new PR was created.</strong><br>
      The previous fix (above) should resolve this error.
      Please verify it has been deployed to <strong>{domain or "the affected domain"}</strong>.
    </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body      {{ font-family: Arial, sans-serif; background:#f9fafb; color:#1f2937; margin:0; padding:20px; }}
    .card     {{ background:#ffffff; border-radius:8px; padding:28px 32px; max-width:640px;
                 margin:0 auto; box-shadow:0 1px 4px rgba(0,0,0,0.08); }}
    .badge    {{ display:inline-block; background:#fef3c7; color:#92400e;
                 border-radius:4px; padding:3px 10px; font-size:13px; font-weight:600; }}
    .section  {{ margin-top:20px; }}
    .label    {{ font-size:12px; color:#6b7280; text-transform:uppercase;
                 letter-spacing:.05em; margin-bottom:4px; }}
    .value    {{ font-size:15px; word-break:break-all; }}
    .code     {{ background:#f3f4f6; border-radius:4px; padding:10px 14px;
                 font-family:monospace; font-size:13px; white-space:pre-wrap; }}
    .footer   {{ margin-top:28px; font-size:12px; color:#9ca3af; border-top:1px solid #e5e7eb;
                 padding-top:14px; }}
    .highlight{{ color:#dc2626; font-weight:600; }}
  </style>
</head>
<body>
  <div class="card">
    <p style="margin:0 0 6px 0; font-size:20px; font-weight:700;">🤖 AutoFix Agent — Known Error Alert</p>
    {badge}

    <div class="section">
      <div class="label">Error</div>
      <div class="code highlight">{error_message}</div>
    </div>

    <div class="section">
      <div class="label">Domain</div>
      <div class="value">{domain or "N/A"}</div>
    </div>

    <div class="section">
      <div class="label">Similarity Score</div>
      <div class="value">{similarity_score:.4f} (threshold {os.getenv("SIMILARITY_THRESHOLD", "0.85")})</div>
    </div>

    <div class="section">
      <div class="label">Original Fix — Commit</div>
      <div class="code">{commit_id}</div>
    </div>

    <div class="section">
      <div class="label">{pr_label}</div>
      <div class="value">{pr_link}</div>
    </div>
    {action_banner}

    <div class="footer">
      Sent by AutoFix Agent &nbsp;|&nbsp; Do not reply to this email.
    </div>
  </div>
</body>
</html>
""".strip()


def send_known_error_email(
    error_message: str,
    commit_id: str,
    pr_url: str | None,
    similarity_score: float,
    domain: str | None,
    forward_ported: bool = False,
) -> None:
    """
    Send an alert email when a known error is detected (similarity >= threshold).
    Uses the internal Bizom notification service.

    forward_ported=True  → pr_url is a brand-new forward-port PR on the current
                           deployment tag; email says "review & merge this PR".
    forward_ported=False → pr_url is the original historical PR; email says
                           "no new PR, verify the old fix is deployed".
    """
    if forward_ported:
        subject = f"[AutoFix] Forward-port PR created for {domain or 'unknown domain'} — review required"
    else:
        subject = f"[AutoFix] Known error on {domain or 'unknown domain'} — fix already exists"

    body = _build_known_error_html(
        error_message=error_message,
        commit_id=commit_id,
        pr_url=pr_url,
        similarity_score=similarity_score,
        domain=domain,
        forward_ported=forward_ported,
    )
    _post_notification_email(
        message=body,
        subject=subject,
        company_id=NOTIFICATION_COMPANY_ID,
    )
