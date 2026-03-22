# Task 001 — Project Setup + Gmail Search Tool

## Goal

Set up the full project skeleton and implement a working `search_email` tool that returns structured `EmailData` from Gmail, and a `get_user_profile` function that returns the authenticated user's email address and display name.

---

## Scope

- Create all files and directories defined in `architecture.md`
- Implement `models.py` (data classes and exceptions only)
- Implement `config.py` (credential loading only)
- Implement `tools/gmail_search.py` (`search_email` and `get_user_profile` functions)
- Write a minimal `main.py` that calls `search_email` and prints the result (temporary, for verification only)

Do NOT implement `agent.py`, `gmail_send.py`, or `openai_generate.py` in this task.

---

## Step-by-Step Instructions

### Step 1 — Create directory structure

```
email_agent/
├── main.py
├── agent.py              # empty stub, do not implement
├── tools/
│   ├── __init__.py       # empty
│   ├── gmail_search.py
│   ├── gmail_send.py     # empty stub
│   └── openai_generate.py  # empty stub
├── models.py
├── config.py
└── requirements.txt
```

Stub files MUST contain only a module-level docstring and a `# TODO` comment. No placeholder logic.

### Step 2 — Implement `models.py`

Define exactly:
- `EmailData` dataclass with fields: `message_id`, `thread_id`, `from_`, `subject`, `body`, `date` (all `str`)
- `SendResult` dataclass with fields: `success` (`bool`), `sent_message_id` (`str`)
- Exception classes: `EmailNotFoundError`, `GmailAPIError`, `OpenAIError`, `SendFailedError` (all extend `Exception`, no custom `__init__`)

No other content in this file.

### Step 3 — Implement `config.py`

Define a `Config` dataclass with fields:
- `gmail_credentials_path: str` — path to `credentials.json`
- `gmail_token_path: str` — path to `token.json` (OAuth token cache)
- `openai_api_key: str`
- `openai_model: str`

Define a `load_config() -> Config` function that:
1. Reads `GMAIL_CREDENTIALS_PATH` (default: `credentials.json`)
2. Reads `GMAIL_TOKEN_PATH` (default: `token.json`)
3. Reads `OPENAI_API_KEY` — MUST raise `EnvironmentError("OPENAI_API_KEY is not set")` if missing
4. Reads `OPENAI_MODEL` (default: `gpt-4o`)
5. Returns a `Config` instance

MUST NOT contain any logic beyond reading environment variables and constructing `Config`.

### Step 4 — Implement `tools/gmail_search.py`

Implement `search_email(subject: str, config: Config) -> EmailData` following the spec in `tools.md` and `api-contracts.md`.

Authentication flow:
1. If `config.gmail_token_path` exists, load token from file using `google.oauth2.credentials.Credentials`.
2. If token is expired and has a refresh token, refresh it and save back to `config.gmail_token_path`.
3. If no valid token exists, run `InstalledAppFlow` using `config.gmail_credentials_path` with scope `https://www.googleapis.com/auth/gmail.modify`. Save the resulting token to `config.gmail_token_path`.

Search flow:
1. Validate `subject`: raise `ValueError("subject must be a non-empty string")` if empty or not a str.
2. Call `users.messages.list(userId='me', q=f'subject:{subject}', maxResults=1)`.
3. If the response has no `messages`, raise `EmailNotFoundError(f"No email found with subject: {subject}")`.
4. Call `users.messages.get(userId='me', id=message_id, format='full')`.
5. Parse headers: extract `From`, `Subject`, `Date` from `payload.headers`.
6. Parse body: walk `payload.parts` to find `mimeType == 'text/plain'`. Decode `data` from base64url using `base64.urlsafe_b64decode`. If no `parts`, use `payload.body.data`.
7. Return `EmailData(message_id=..., thread_id=..., from_=..., subject=..., body=..., date=...)`.

Wrap all Gmail API calls in try/except and raise `GmailAPIError(str(e))` on `googleapiclient.errors.HttpError`.

### Step 4b — Implement `get_user_profile` in `tools/gmail_search.py`

Implement `get_user_profile(config: Config) -> tuple[str, str]`.

This function returns `(email, display_name)` for the authenticated Gmail user so that generated replies can be signed with the user's real name rather than their email address.

Implementation:
1. Reuse `_build_service(config)` — no new auth logic needed.
2. Call `users().settings().sendAs().list(userId='me')`.
3. Iterate the returned `sendAs` list and find the entry where `isPrimary == True`.
4. Return `(alias["sendAsEmail"], alias.get("displayName", ""))`.
5. If no primary alias is found (edge case), fall back to `users().getProfile(userId='me')` and return `(profile["emailAddress"], "")`.
6. Wrap all API calls in try/except and raise `GmailAPIError` on `HttpError`.

The display name is whatever the user has set in **Gmail Settings → General → Name**. It may be an empty string if the user has not configured one.

### Step 5 — Implement `requirements.txt`

```
google-api-python-client==2.126.0
google-auth-oauthlib==1.2.0
openai==2.29.0
python-dotenv>=1.0.0
```

Pin exact versions. No other dependencies.

### Step 6 — Implement temporary `main.py`

```python
import logging
from config import load_config
from tools.gmail_search import search_email

logging.basicConfig(level=logging.DEBUG)

config = load_config()
subject = input("Enter email subject to search: ").strip()
email = search_email(subject, config)
print(f"From: {email.from_}")
print(f"Subject: {email.subject}")
print(f"Date: {email.date}")
print(f"Body:\n{email.body}")
```

This is temporary scaffolding for acceptance testing. It will be replaced in task 002.

---

## Acceptance Criteria

- [ ] Running `python main.py` prompts for a subject, calls Gmail, and prints a real email's fields.
- [ ] If the subject matches no email, the program prints `"No email found with subject: <input>"` and exits without a traceback.
- [ ] If `OPENAI_API_KEY` is not set, `load_config()` raises `EnvironmentError` with the variable name in the message.
- [ ] If `credentials.json` is missing, the Gmail auth flow raises a clear error (not a silent failure).
- [ ] `EmailData` fields are all populated (no empty strings for `from_`, `subject`, `body`, `date`).
- [ ] `get_user_profile(config)` returns a `tuple[str, str]` of `(email, display_name)`.
- [ ] `get_user_profile` returns the display name configured in Gmail Settings when one is set.
- [ ] `get_user_profile` returns `""` for `display_name` when no name is configured, without raising.
- [ ] `get_user_profile` raises `GmailAPIError` on any Gmail API failure.
- [ ] No credentials appear in any log output at `INFO` or above.
- [ ] All functions in `gmail_search.py` are ≤30 lines of logic each.

---

## Edge Cases to Handle

| Case | Expected behavior |
|---|---|
| Subject matches multiple emails | Return only the most recent (first result from Gmail) |
| Email has no `text/plain` part (HTML-only) | Fall back to stripping tags; if still empty raise `GmailAPIError("Could not extract plain text body")` |
| Email body is base64-encoded with padding issues | Use `base64.urlsafe_b64decode` with `+ "=="` padding; do not raise on padding errors |
| `Date` header missing from email | Set `date` to empty string `""` rather than raising |
| Gmail API returns HTTP 401 | Raise `GmailAPIError("Gmail authentication failed: 401")` |
| Gmail API returns HTTP 429 | Raise `GmailAPIError("Gmail rate limit exceeded: 429")` |
| `subject` input contains special characters (`:`, `"`) | Pass as-is to the Gmail query; do not sanitize |

---

## Edge Cases — `get_user_profile`

| Case | Expected behavior |
|---|---|
| User has a display name set in Gmail | Return it as `display_name` |
| User has no display name set | Return `""` for `display_name` — do not raise |
| No primary `sendAs` alias found | Fall back to `getProfile` for email; return `""` for name |
| Gmail API returns HTTP 401 | Raise `GmailAPIError("Gmail authentication failed: 401")` |
| Gmail API returns HTTP 429 | Raise `GmailAPIError("Gmail rate limit exceeded: 429")` |

---

## Out of Scope for This Task

- Sending emails
- Generating replies
- Agent loop
- Any user interaction beyond the temporary `main.py` input prompt
