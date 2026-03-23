# API Contracts

All tool functions use Python typed signatures. JSON structures below represent the shape of data passed between layers, matching the `models.py` dataclasses exactly.

---

## search_email(subject: str) → EmailData

Searches Gmail for the most recent email whose subject contains `subject` (case-insensitive).

### Input

```json
{
  "subject": "string — non-empty, partial match allowed"
}
```

### Output (EmailData)

```json
{
  "message_id": "string — Gmail message ID",
  "thread_id": "string — Gmail thread ID, required for reply",
  "from": "string — sender email address",
  "subject": "string — full subject line of the matched email",
  "body": "string — plain text body of the email, decoded from MIME",
  "date": "string — ISO 8601 datetime string, e.g. '2026-03-19T10:00:00Z'"
}
```

### Errors

| Condition | Exception |
|---|---|
| `subject` is empty or not a string | `ValueError` |
| Gmail API authentication fails | `GmailAPIError` |
| No email matches the subject | `EmailNotFoundError` |
| Gmail API returns unexpected response | `GmailAPIError` |

### Notes

- Returns only the **most recent** match when multiple emails match.
- `body` MUST be plain text. If the email is multipart, extract `text/plain`. If unavailable, strip HTML tags as a fallback.
- `thread_id` MUST be preserved exactly as returned by Gmail — it is required by `send_email`.

---

## generate_reply(email_content: str, from_: str, config: Config, user_email: str = "", user_name: str = "", feedback: str = "") → ReplyResult

Calls the OpenAI API to generate a reply to the given email body.

### Input

```json
{
  "email_content": "string — plain text email body, non-empty",
  "from_": "string — sender address of the original email, non-empty",
  "config": "Config — application config (provides OpenAI key and model)",
  "user_email": "string — the authenticated user's email address, used to sign the reply (optional)",
  "user_name": "string — the authenticated user's display name, used to sign the reply (optional)",
  "feedback": "string — revision instructions from the user; empty string for first draft (optional)"
}
```

`user_email` and `user_name` are fetched from the Gmail user profile so the generated reply is signed correctly. They are optional — the model falls back to generic attribution when omitted.

### Output (ReplyResult)

```json
{
  "reply": "string — generated reply text, plain text, non-empty",
  "recipient": "string — email address the reply should be sent to"
}
```

### Errors

| Condition | Exception |
|---|---|
| `email_content` or `from_` is empty or not a string | `ValueError` |
| OpenAI API key missing or invalid | `OpenAIError` |
| OpenAI API returns empty or null content | `OpenAIError` |
| OpenAI API rate limit or network failure | `OpenAIError` |

### Notes

- MUST use the `gpt-4o` model unless overridden by the `OPENAI_MODEL` environment variable.
- MUST send a system prompt instructing the model to write a professional email reply.
- MUST NOT post-process or truncate the model's response before returning it.
- Uses OpenAI Structured Outputs to guarantee `reply` and `recipient` fields in the response.

---

## send_email(reply: str, thread_id: str) → SendResult

Sends `reply` as a reply within the Gmail thread identified by `thread_id`.

### Input

```json
{
  "reply": "string — plain text reply body, non-empty",
  "thread_id": "string — Gmail thread ID from EmailData, non-empty"
}
```

### Output (SendResult)

```json
{
  "success": true,
  "sent_message_id": "string — Gmail message ID of the sent message"
}
```

### Errors

| Condition | Exception |
|---|---|
| `reply` or `thread_id` is empty or not a string | `ValueError` |
| Gmail API authentication fails | `GmailAPIError` |
| Thread not found | `SendFailedError` |
| Gmail API returns send failure | `SendFailedError` |

### Notes

- The sent message MUST be threaded (i.e., include `threadId` in the Gmail API request body).
- MUST set the `Content-Type` of the message to `text/plain`.
- MUST NOT send if `reply` is whitespace-only (treat as empty).

---

## Shared Models (models.py reference)

```python
@dataclass
class EmailData:
    message_id: str
    thread_id: str
    from_: str            # field name: from_ (avoids Python keyword conflict)
    subject: str
    body: str
    date: str
    message_id_header: str  # RFC 2822 Message-ID header, used for In-Reply-To threading

@dataclass
class SendResult:
    success: bool
    sent_message_id: str

@dataclass
class ReplyResult:
    reply: str        # generated reply body
    recipient: str    # email address the reply should be sent to

class EmailNotFoundError(Exception): pass
class GmailAPIError(Exception): pass
class OpenAIError(Exception): pass
class SendFailedError(Exception): pass
```
