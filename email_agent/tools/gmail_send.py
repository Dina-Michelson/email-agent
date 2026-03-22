"""Gmail send tool — sends an approved reply as a threaded Gmail message."""
import base64
import logging
from email.mime.text import MIMEText

from googleapiclient.errors import HttpError

from config import Config
from models import EmailData, GmailAPIError, SendFailedError, SendResult
from tools.gmail_search import _build_service

logger = logging.getLogger(__name__)


def send_reply(email: EmailData, reply_body: str, config: Config) -> SendResult:
    """Send reply_body as a threaded reply to email.

    Sets In-Reply-To and References so Gmail groups it into the same thread.
    """
    if not reply_body or not reply_body.strip():
        raise ValueError("reply_body must be a non-empty string")

    service = _build_service(config)

    to_address = email.from_
    subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"

    mime = MIMEText(reply_body, "plain", "utf-8")
    mime["To"] = to_address
    mime["Subject"] = subject

    if email.message_id_header:
        mime["In-Reply-To"] = email.message_id_header
        mime["References"] = email.message_id_header

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
    body = {"raw": raw, "threadId": email.thread_id}

    logger.debug("Sending reply to=%s subject=%s thread=%s", to_address, subject, email.thread_id)

    try:
        sent = service.users().messages().send(userId="me", body=body).execute()
    except HttpError as e:
        status = e.resp.status
        if status == 401:
            raise GmailAPIError("Gmail authentication failed: 401") from e
        if status == 429:
            raise GmailAPIError("Gmail rate limit exceeded: 429") from e
        raise SendFailedError(f"Gmail send failed: {status}") from e

    sent_id = sent.get("id", "")
    logger.debug("Reply sent message_id=%s", sent_id)
    return SendResult(success=True, sent_message_id=sent_id)
