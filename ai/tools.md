# Tools

## Overview

There are three tools. Each is a standalone Python function in `tools/`. The agent calls them in sequence. Tools have no awareness of each other.

---

## Tool 1: gmail_search — `tools/gmail_search.py`

### Purpose
Find the most recent Gmail message whose subject matches the user's query.

### Function Signature
```python
def search_email(subject: str, config: Config) -> EmailData
```

### Inputs
| Parameter | Type | Description |
|---|---|---|
| `subject` | `str` | Partial or full subject string to search for |
| `config` | `Config` | Loaded credentials and settings from `config.py` |

### Output
Returns an `EmailData` instance (see `api-contracts.md`).

### When the agent calls this tool
At the start of every run, immediately after receiving the user's subject input. Called exactly once per run.

### Implementation notes
- Authenticate using OAuth2 credentials stored at the path in `config.gmail_credentials_path`. Token cache stored at `config.gmail_token_path`.
- Use Gmail API query: `subject:{subject}` with `maxResults=1` and `orderBy` descending by date.
- Fetch full message body using `messages.get(format='full')`.
- Parse `payload.parts` to extract `text/plain` content. Decode from base64url.
- MUST NOT modify the raw body content beyond decoding.

---

## Tool 2: openai_generate — `tools/openai_generate.py`

### Purpose
Generate a professional reply to an email body using the OpenAI API.

### Function Signature
```python
def generate_reply(email_content: str, config: Config) -> str
```

### Inputs
| Parameter | Type | Description |
|---|---|---|
| `email_content` | `str` | Plain text body of the received email |
| `config` | `Config` | Contains `openai_api_key` and `openai_model` |

### Output
Returns a plain `str` — the generated reply text.

### When the agent calls this tool
After `search_email` succeeds and the email has been displayed to the user. Called exactly once per run (not re-called on user modification — the modified text replaces the output directly).

### Implementation notes
- Use the `openai` Python SDK (`openai.OpenAI` client).
- System prompt MUST be: `"You are a professional assistant. Write a concise, polite reply to the following email."`.
- Pass `email_content` as the user message.
- Use `config.openai_model` (default `gpt-4o`).
- Return `response.choices[0].message.content` exactly. Do not strip or reformat.

---

## Tool 3: gmail_send — `tools/gmail_send.py`

### Purpose
Send the approved reply as a threaded Gmail message.

### Function Signature
```python
def send_email(reply: str, thread_id: str, config: Config) -> SendResult
```

### Inputs
| Parameter | Type | Description |
|---|---|---|
| `reply` | `str` | Plain text reply body approved by the user |
| `thread_id` | `str` | Gmail thread ID from the original `EmailData` |
| `config` | `Config` | Loaded credentials |

### Output
Returns a `SendResult` instance (see `api-contracts.md`).

### When the agent calls this tool
Only after the user explicitly approves the reply. MUST NOT be called on rejection or if the agent loop exits early for any reason.

### Implementation notes
- Build a MIME message (`email.mime.text.MIMEText`) with `Content-Type: text/plain`.
- Encode the message to base64url bytes and pass as `raw` in the Gmail API request body.
- Include `threadId` in the request body to ensure threading.
- Call `users.messages.send(userId='me', body={...})`.
- Return `SendResult(success=True, sent_message_id=response['id'])` on success.
- Raise `SendFailedError` if the API response does not include `'id'`.

---

## Tool Call Decision Table

| Agent state | Tool to call | Condition to skip |
|---|---|---|
| User provided subject | `search_email` | Never skipped |
| `search_email` returned EmailData | `generate_reply` | Skip if `search_email` raised an exception |
| User approved reply | `send_email` | Skip if user rejected or modified and re-rejected |
| User modified reply | No tool call | Use modified text directly; do not re-call `generate_reply` |
