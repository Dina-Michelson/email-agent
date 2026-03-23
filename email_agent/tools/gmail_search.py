import base64
import logging
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config
from models import EmailData, EmailNotFoundError, GmailAPIError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send"]


def get_user_profile(config: Config) -> tuple[str, str]:
    """Return (email, display_name) for the authenticated Gmail user.

    Uses the primary sendAs alias, which carries the display name the user
    has configured in Gmail Settings → General → Name.
    Falls back to an empty string for display_name if none is set.
    """
    try:
        service = _build_service(config)
        send_as_list = service.users().settings().sendAs().list(userId="me").execute()
        for alias in send_as_list.get("sendAs", []):
            if alias.get("isPrimary"):
                return alias["sendAsEmail"], alias.get("displayName", "")
        # Fallback: no primary alias found, use getProfile for email only
        profile = service.users().getProfile(userId="me").execute()
        return profile["emailAddress"], ""
    except HttpError as e:
        raise GmailAPIError(_http_error_message(e)) from e


def search_email(subject: str, config: Config) -> EmailData:
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be a non-empty string")

    logger.debug("Searching Gmail for subject: %s", subject)
    service = _build_service(config)

    try:
        result = service.users().messages().list(
            userId="me", q=f"subject:{subject}", maxResults=1
        ).execute()
    except HttpError as e:
        raise GmailAPIError(_http_error_message(e)) from e

    messages = result.get("messages", [])
    if not messages:
        raise EmailNotFoundError(f"No email found with subject: {subject}")

    message = _fetch_message(service, messages[0]["id"])
    payload = message.get("payload", {})
    from_, subject_header, date, message_id_header = _parse_headers(payload.get("headers", []))
    body = _extract_body(payload)

    if not body:
        raise GmailAPIError("Could not extract plain text body")

    logger.debug("Found email message_id=%s from=%s", message["id"], from_)
    return EmailData(
        message_id=message["id"],
        thread_id=message["threadId"],
        from_=from_,
        subject=subject_header,
        body=body,
        date=date,
        message_id_header=message_id_header,
    )


def _build_service(config: Config):
    creds = _get_credentials(config)
    return build("gmail", "v1", credentials=creds)


def _get_credentials(config: Config) -> Credentials:
    creds = None

    if os.path.exists(config.gmail_token_path):
        creds = Credentials.from_authorized_user_file(config.gmail_token_path, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds, config.gmail_token_path)
        return creds

    if creds and creds.valid:
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(config.gmail_credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds, config.gmail_token_path)
    return creds


def _save_token(creds: Credentials, token_path: str) -> None:
    with open(token_path, "w") as f:
        f.write(creds.to_json())


def _fetch_message(service, message_id: str) -> dict:
    try:
        return service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    except HttpError as e:
        raise GmailAPIError(_http_error_message(e)) from e


def _parse_headers(headers: list) -> tuple:
    header_map = {h["name"]: h["value"] for h in headers}
    return (
        header_map.get("From", ""),
        header_map.get("Subject", ""),
        header_map.get("Date", ""),
        header_map.get("Message-ID", ""),
    )


def _extract_body(payload: dict) -> str:
    parts = payload.get("parts", [])
    if parts:
        return _extract_from_parts(parts)

    data = payload.get("body", {}).get("data", "")
    return _decode_part(data) if data else ""


def _extract_from_parts(parts: list) -> str:
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return _decode_part(data)

    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                return _strip_html(_decode_part(data))

    return ""


def _decode_part(data: str) -> str:
    padded = data + "=="
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _http_error_message(e: HttpError) -> str:
    status = e.resp.status
    if status == 401:
        return "Gmail authentication failed: 401"
    if status == 429:
        return "Gmail rate limit exceeded: 429"
    return f"Gmail API error: {status}"
