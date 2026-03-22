# Coding Standards

## Error Handling

- Every tool function MUST raise a specific exception on failure. MUST NOT return `None`, empty strings, or dicts with an `"error"` key to signal failure.
- Define custom exceptions in `models.py`: `EmailNotFoundError`, `GmailAPIError`, `OpenAIError`, `SendFailedError`.
- `agent.py` MUST catch each exception at the call site and handle it explicitly. A bare `except Exception` is ONLY allowed in `main.py` as a last-resort handler.
- MUST NOT swallow exceptions silently (no empty `except` blocks).

```python
# Correct
try:
    email = search_email(subject)
except EmailNotFoundError:
    print(f"No email found matching: {subject}")
    return

# Incorrect
email = search_email(subject)
if not email:
    ...
```

---

## API Key Handling

- MUST NOT hardcode any credentials, tokens, or keys anywhere in source files.
- MUST NOT commit `.env` files or `credentials.json` to version control. Add them to `.gitignore`.
- All credentials MUST be loaded in `config.py` using `os.environ`. If a required variable is missing, `config.py` MUST raise `EnvironmentError` with the variable name.
- Tools receive credentials via the `Config` object passed at initialization or as a parameter. Tools MUST NOT call `os.environ` directly.

---

## Logging

- MUST use Python's built-in `logging` module. MUST NOT use `print()` for diagnostic output (only for user-facing prompts and display).
- Log level MUST be configurable via the `LOG_LEVEL` environment variable. Default to `WARNING`.
- Each module MUST create its own logger: `logger = logging.getLogger(__name__)`.
- Log at `DEBUG` for tool inputs/outputs, `INFO` for agent state transitions, `ERROR` for caught exceptions before re-raise or handling.
- MUST NOT log credentials, full email bodies at `INFO` or above, or API keys at any level.

---

## Function Size

- Each function MUST do one thing. If a function requires more than ~30 lines of logic (excluding docstring and blank lines), split it.
- Tool functions MUST be pure in effect: one network call, one return, no side effects beyond that call.
- `agent.py` functions are allowed multiple tool calls but MUST NOT contain parsing, formatting, or API-client logic inline.

---

## Separation of Concerns

| Layer | Allowed | Not Allowed |
|---|---|---|
| `main.py` | Start agent, configure logging | Business logic, tool calls |
| `agent.py` | Orchestrate tools, user I/O | API client code, credential loading |
| `tools/*.py` | API calls, data parsing | User I/O, calling other tools |
| `config.py` | Load env vars, build Config | Any logic beyond loading |
| `models.py` | Data classes, exceptions | Any logic |

---

## Input Validation

- `search_email(subject)`: MUST validate that `subject` is a non-empty string before calling the Gmail API. Raise `ValueError` if invalid.
- `send_email(reply, thread_id)`: MUST validate that both `reply` and `thread_id` are non-empty strings. Raise `ValueError` if invalid.
- `generate_reply(email_content)`: MUST validate that `email_content` is a non-empty string. Raise `ValueError` if invalid.
- Validation MUST happen at the top of each tool function, before any external call.

---

## Dependencies

- MUST NOT add a dependency that can be replaced by the standard library.
- MUST pin all dependency versions in `requirements.txt` (e.g., `google-api-python-client==2.x.x`).
- Allowed external packages: `google-api-python-client`, `google-auth-oauthlib`, `openai`. No others without explicit justification in a comment in `requirements.txt`.
