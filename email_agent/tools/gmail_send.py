"""Gmail send tool — sends an approved reply as a threaded Gmail message."""
import base64
import logging
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from googleapiclient.errors import HttpError

from config import Config
from models import EmailData, GmailAPIError, SendFailedError, SendResult
from tools.gmail_search import _build_service

logger = logging.getLogger(__name__)


def send_reply(email: EmailData, reply_body: str, config: Config, recipient: str = "") -> SendResult:
    """Send reply_body as a threaded reply to email.

    Sets In-Reply-To and References so Gmail groups it into the same thread.
    recipient overrides the auto-derived to_address when provided.
    """
    if not reply_body or not reply_body.strip():
        raise ValueError("reply_body must be a non-empty string")

    service = _build_service(config)

    to_address = recipient.strip() if recipient.strip() else email.from_
    subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"

    name, addr = parseaddr(to_address)
    encoded_to = formataddr((str(Header(name, "utf-8")) if name else "", addr))

    mime = MIMEText(reply_body, "plain", "utf-8")
    mime["To"] = encoded_to
    mime["Subject"] = subject

    # Build References from all message IDs in the thread (required for inbox conversation grouping)
    all_ids = [m.get("message_id_header", "") for m in email.thread_messages if m.get("message_id_header")]
    if not all_ids and email.message_id_header:
        all_ids = [email.message_id_header]
    if all_ids:
        mime["In-Reply-To"] = all_ids[-1]
        mime["References"] = " ".join(all_ids)

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
    body = {"raw": raw, "threadId": email.thread_id}

    logger.debug("Sending reply to=%s subject=%s thread=%s", to_address, subject, email.thread_id)

    try:
        sent = service.users().messages().send(userId="me", body=body).execute()
    except HttpError as e:
        status = e.resp.status
        logger.error("Gmail send HttpError %s: %s", status, e.content)
        if status == 401:
            raise GmailAPIError("Gmail authentication failed: 401") from e
        if status == 429:
            raise GmailAPIError("Gmail rate limit exceeded: 429") from e
        raise SendFailedError(f"Gmail send failed: {status}") from e

    sent_id = sent.get("id", "")
    logger.debug("Reply sent message_id=%s", sent_id)
    return SendResult(success=True, sent_message_id=sent_id)


def check_delivery_failure(config: Config, sent_at: float, recipient: str, wait_seconds: int = 8) -> bool:
    """Wait briefly, then check Gmail for a bounce / delivery-failure notification.

    Only considers messages received after sent_at (Unix timestamp) whose
    snippet mentions the recipient address, to avoid false positives from
    delayed bounces belonging to earlier sends.
    Returns True if a delivery failure for this recipient is detected, False otherwise.
    """
    time.sleep(wait_seconds)
    service = _build_service(config)
    after_ts = int(sent_at)
    query = (
        f"after:{after_ts} "
        "("
        "from:mailer-daemon "
        "OR subject:\"delivery failed\" "
        "OR subject:\"Delivery Status Notification\" "
        "OR subject:\"Undeliverable\""
        ")"
    )
    try:
        result = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = result.get("messages", [])
        if not messages:
            return False
        # Confirm at least one bounce mentions the recipient we sent to.
        recipient_addr = recipient.lower().strip()
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["To", "Subject"],
            ).execute()
            snippet = detail.get("snippet", "").lower()
            if recipient_addr in snippet:
                return True
        return False
    except HttpError as e:
        logger.warning("Bounce check failed: %s", e)
        return False
