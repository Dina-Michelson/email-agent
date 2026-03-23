# Task 004 — Gmail Send Tool

## Goal

Implement `tools/gmail_send.py` — a standalone tool that sends an approved reply email through the Gmail API, preserving the original thread using RFC 2822 headers.

Also update `tools/gmail_search.py` to populate the `message_id_header` field on `EmailData`, which `send_reply` depends on for thread linking.

---

## Scope

- Implement `tools/gmail_send.py` (`send_reply` function)
- Update `tools/gmail_search.py` to parse and populate `EmailData.message_id_header`

Do NOT modify `agent.py`, `models.py`, `config.py`, or `main.py` in this task.

---

## Architecture

```
agent.py
  └── _exec_send_email()
        └── send_reply(email, reply_body, config)   ← this task
              └── Gmail API  users.messages.send()
```

The tool is called by the agent after the user approves the draft. The tool does not interact with the user, control the conversation, or generate email content.

---

## Thread Preservation Requirement

**The reply MUST be delivered inside the same Gmail thread as the original email.**

This is a hard requirement, not optional. A reply that creates a new thread is incorrect behavior.

Thread preservation requires two independent mechanisms, both of which MUST be applied:

| Mechanism | How | What it does |
|---|---|---|
| Gmail thread grouping | Pass `"threadId": email.thread_id` in the API request body | Tells Gmail to place the message in the existing thread |
| RFC 2822 header linking | Set `In-Reply-To` and `References` to `email.message_id_header` | Allows email clients outside Gmail to group the conversation |

Both must be applied together. Using only `threadId` works within Gmail but breaks threading in other email clients. Using only the RFC 2822 headers works for external clients but may create a new thread in Gmail if the `threadId` is absent.

If `email.thread_id` is empty, pass it anyway — Gmail will handle the fallback. If `email.message_id_header` is empty, skip the RFC 2822 headers silently (do not raise).

---

## Function Signature

```python
def send_reply(email: EmailData, reply_body: str, config: Config) -> SendResult:
```

| Parameter | Type | Description |
|---|---|---|
| `email` | `EmailData` | The email being replied to (from `search_email`) |
| `reply_body` | `str` | The approved reply body text (from `generate_reply`) |
| `config` | `Config` | Runtime configuration (credentials paths) |

Returns `SendResult(success=True, sent_message_id=<id>)` on success.
Raises `GmailAPIError` or `SendFailedError` on failure. Never returns a partial result.

---

## Step-by-Step Instructions

### Step 1 — Validate input

At the start of `send_reply`, raise `ValueError("reply_body must be a non-empty string")` if `reply_body` is empty or whitespace-only. Do not call the Gmail API with an empty body.

### Step 2 — Authenticate with Gmail

Reuse `_build_service(config)` from `tools/gmail_search.py`. Do not duplicate authentication logic.

```python
from tools.gmail_search import _build_service

service = _build_service(config)
```

### Step 3 — Resolve recipient and subject

Extract the recipient address and subject from `email`:

```python
to_address = email.from_
subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
```

### Step 4 — Construct the MIME message

Build a `MIMEText` message with UTF-8 encoding:

```python
from email.mime.text import MIMEText

mime = MIMEText(reply_body, "plain", "utf-8")
mime["To"] = to_address
mime["Subject"] = subject
```

If `email.message_id_header` is non-empty, add RFC 2822 threading headers so Gmail groups the reply into the original thread:

```python
if email.message_id_header:
    mime["In-Reply-To"] = email.message_id_header
    mime["References"] = email.message_id_header
```

### Step 5 — Encode and send

Encode the MIME message as base64url and send it via the Gmail API. Pass `threadId` so Gmail places the message in the same thread:

```python
import base64

raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
body = {"raw": raw, "threadId": email.thread_id}
sent = service.users().messages().send(userId="me", body=body).execute()
```

### Step 6 — Return structured result

Extract the sent message ID from the response and return a `SendResult`:

```python
sent_id = sent.get("id", "")
return SendResult(success=True, sent_message_id=sent_id)
```

### Step 7 — Handle Gmail API errors

Wrap the `service.users().messages().send()` call in a try/except block:

```python
from googleapiclient.errors import HttpError

try:
    sent = service.users().messages().send(userId="me", body=body).execute()
except HttpError as e:
    status = e.resp.status
    if status == 401:
        raise GmailAPIError("Gmail authentication failed: 401") from e
    if status == 429:
        raise GmailAPIError("Gmail rate limit exceeded: 429") from e
    raise SendFailedError(f"Gmail send failed: {status}") from e
```

Do not catch generic `Exception`. Let unexpected errors propagate — the agent handles them.

### Step 8 — Add logging

Add a module-level logger and log the outgoing send at `DEBUG`:

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Sending reply to=%s subject=%s thread=%s", to_address, subject, email.thread_id)
logger.debug("Reply sent message_id=%s", sent_id)
```

Never log `reply_body` content at `INFO` or above.

---

## Update `tools/gmail_search.py` — Populate `message_id_header`

The `send_reply` function uses `email.message_id_header` to set `In-Reply-To` and `References` headers. This field must be populated by `search_email`.

In the header-parsing section of `search_email`, extract the `Message-ID` header alongside `From`, `Subject`, and `Date`:

```python
message_id_header = ""
for header in headers:
    name = header.get("name", "").lower()
    if name == "from":
        from_ = header.get("value", "")
    elif name == "subject":
        subject = header.get("value", "")
    elif name == "date":
        date = header.get("value", "")
    elif name == "message-id":
        message_id_header = header.get("value", "")
```

Pass `message_id_header` when constructing `EmailData`:

```python
return EmailData(
    message_id=...,
    thread_id=...,
    from_=from_,
    subject=subject,
    body=...,
    date=date,
    message_id_header=message_id_header,
)
```

`message_id_header` already has a default of `""` in `models.py`, so this change is backwards-compatible. If the header is absent, threading is skipped gracefully (the `if email.message_id_header:` guard in `send_reply` handles this).

---

## Models Reference

These types are already defined in `models.py`. Do not redefine them.

```python
@dataclass
class EmailData:
    message_id: str
    thread_id: str
    from_: str
    subject: str
    body: str
    date: str
    message_id_header: str = ""   # RFC 2822 Message-ID (used for threading)

@dataclass
class SendResult:
    success: bool
    sent_message_id: str

class GmailAPIError(Exception): pass
class SendFailedError(Exception): pass
```

---

## Error Handling

| Scenario | Expected behavior |
|---|---|
| `reply_body` is empty or whitespace | Raise `ValueError("reply_body must be a non-empty string")` before calling Gmail |
| Gmail API returns HTTP 401 | Raise `GmailAPIError("Gmail authentication failed: 401")` |
| Gmail API returns HTTP 429 | Raise `GmailAPIError("Gmail rate limit exceeded: 429")` |
| Gmail API returns any other HTTP error | Raise `SendFailedError(f"Gmail send failed: {status}")` |
| `email.message_id_header` is empty | Send without threading headers — do not raise |
| `email.thread_id` is empty | Pass empty `threadId` to Gmail API — do not raise |

Never return a success result if the API call failed. Never swallow exceptions silently.

---

## Authentication

Authentication is handled entirely by `_build_service(config)` (already implemented in `tools/gmail_search.py`). `send_reply` does not perform OAuth, load tokens, or read credential files.

The Gmail scope required for sending is `https://www.googleapis.com/auth/gmail.modify`, which is already requested during the OAuth flow in Task-001.

Do NOT hardcode credentials, email addresses, or API keys. All credential paths come from `config`.

---

## Files to Modify

| File | Action |
|---|---|
| `tools/gmail_send.py` | Replace stub with full implementation |
| `tools/gmail_search.py` | Add `message-id` header extraction when building `EmailData` |

---

## Acceptance Criteria

- [ ] `send_reply(email, reply_body, config)` sends an email via the Gmail API and returns `SendResult(success=True, sent_message_id=<non-empty-string>)`.
- [ ] The sent message appears in the Gmail Sent folder of the authenticated account.
- [ ] When `email.message_id_header` is set, the sent email is grouped into the original thread in Gmail.
- [ ] When `email.message_id_header` is empty, the email is sent without threading headers and no error is raised.
- [ ] `ValueError` is raised immediately if `reply_body` is empty or whitespace-only.
- [ ] `GmailAPIError` is raised on HTTP 401.
- [ ] `GmailAPIError` is raised on HTTP 429.
- [ ] `SendFailedError` is raised on any other Gmail HTTP error.
- [ ] No credentials, API keys, or email body content appear in logs at `INFO` or above.
- [ ] `search_email` populates `EmailData.message_id_header` from the `Message-ID` header when present.
- [ ] `search_email` sets `message_id_header` to `""` when the header is absent — no error raised.
- [ ] The full agent flow works end-to-end: search → draft → approve → send → confirmation.

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| Email has no `Message-ID` header | `message_id_header` is `""`, reply is sent without `In-Reply-To` |
| `reply_body` is only whitespace | `ValueError` raised before API call |
| Gmail returns HTTP 403 (insufficient scope) | `SendFailedError("Gmail send failed: 403")` raised |
| `sent.get("id")` returns `None` | `sent_message_id` is set to `""` — do not raise |
| Subject already starts with `"Re:"` (case-insensitive) | Do not prepend another `"Re:"` |

---

## Out of Scope for This Task

- Sending to multiple recipients (CC/BCC)
- HTML email body formatting
- Attachment handling
- Retry logic on transient failures
- Any changes to `agent.py`, `models.py`, `config.py`, or `main.py`
