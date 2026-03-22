# Task 002 — OpenAI Reply Generation Tool

## Objective

Implement `tools/openai_generate.py` — the tool the conversational agent calls to generate a draft email reply using the OpenAI API, after a Gmail message has been retrieved by `search_email`.

The tool returns **structured output** containing both the generated reply text and the resolved recipient address. The recipient defaults to the most recent sender unless the user specifies a different one in feedback.

---

## Context

Task-001 delivered `search_email`, which the agent calls to retrieve an `EmailData` object (fields: `from_`, `subject`, `body`, `thread_id`, etc.) from Gmail.

Task-002 is the next step in the agent pipeline. After displaying the retrieved email to the user, the agent calls `generate_reply` to produce a suggested reply. The agent then presents that reply — and the resolved recipient — to the user and asks whether to approve, modify, or reject it.

This tool is called as many times as needed per user modification requests, by `agent.py`, after `search_email` succeeds. It has no dependency on Gmail and must not interact with it.

---

## Data Model Change

Add `ReplyResult` to `models.py`:

```python
@dataclass
class ReplyResult:
    reply: str      # generated reply body, plain text
    recipient: str  # resolved recipient email address
```

No other changes to `models.py`.

---

## Tool Specification

### Function Signature

```python
def generate_reply(
    email_content: str,
    from_: str,
    config: Config,
    feedback: str = "",
) -> ReplyResult
```

Located at: `tools/openai_generate.py`

### Input

| Parameter | Type | Default | Description |
|---|---|---|---|
| `email_content` | `str` | required | Plain text body of the received email. Must be non-empty. |
| `from_` | `str` | required | Sender address of the original email (`EmailData.from_`). Used as the default recipient. Must be non-empty. |
| `config` | `Config` | required | Carries `openai_api_key` and `openai_model`. |
| `feedback` | `str` | `""` | User's modification instructions. Empty = first generation. May contain an alternative recipient address. |

`email_content` and `from_` are passed directly from `EmailData` fields by the agent.

When `feedback` is a non-empty string, the tool is being called to **revise** a prior reply. The LLM re-evaluates both the reply body and the recipient based on the feedback.

Conceptual input (for documentation only):

```json
{
  "from": "john@example.com",
  "subject": "Project proposal follow-up",
  "body": "Hi, I wanted to follow up on the proposal we discussed last week..."
}
```

### Output

Returns a `ReplyResult` dataclass instance (defined in `models.py`):

```python
@dataclass
class ReplyResult:
    reply: str      # plain text reply body
    recipient: str  # email address the reply should be sent to
```

Conceptual shape:

```json
{
  "reply": "Hi John, Thank you for following up. I'll review the proposal and get back to you by end of week.",
  "recipient": "john@example.com"
}
```

The recipient is `from_` by default. If feedback instructs a different recipient (e.g. `"send it to mary@example.com instead"`), the LLM sets it accordingly.

---

## Prompt Design

The prompt instructs the LLM to return **JSON only** — no prose, no markdown fences.

### System message

Use this exact string — do not alter it:

```
You are a professional assistant that writes clear, polite, and concise email replies. The recipient should normally be the sender of the original email unless the user explicitly requests a different recipient.
```

### User message — first generation (`feedback` is empty)

```
Original email:
Hi, I wanted to follow up on the proposal we discussed last week...

Sender: john@example.com
```

Exact template:

```python
user_message = f"Original email:\n{email_content}\n\nSender: {from_}"
```

### User message — revision (`feedback` is non-empty)

```
Original email:
Hi, I wanted to follow up on the proposal we discussed last week...

Sender: john@example.com

User feedback:
Make it shorter and send it to mary@example.com instead.
```

Exact template:

```python
user_message = (
    f"Original email:\n{email_content}\n\n"
    f"Sender: {from_}\n\n"
    f"User feedback:\n{feedback}"
)
```

Do not alter the section labels (`"Original email:"`, `"Sender:"`, `"User feedback:"`).

### Rules for the LLM (both modes)

- Maintain a **professional, concise** tone.
- Reference the **content of the original email** — acknowledge the sender's topic or question.
- When feedback is present, **follow it precisely** — treat it as an authoritative instruction.
- If feedback specifies a different recipient, use that address in the `"recipient"` field; otherwise use the sender's address.
- Do **not hallucinate** information not present in `email_content` or `feedback`.
- Do **not add** email headers or labels like `"Subject:"` or `"To:"` inside the reply body.
- The `"reply"` value must be **plain text** suitable for direct use as an email body.
- Return **only** the JSON object. No surrounding text, no markdown code fences.

### API call parameters

| Parameter | Value |
|---|---|
| `model` | `config.openai_model` — do not hardcode |
| `messages` | `[system message, user message]` as described above |
| `response_format` | OpenAI Structured Outputs schema (see below) |

Use OpenAI's **Structured Outputs** feature (`response_format` with `type: "json_schema"`) to guarantee the API returns valid JSON matching the expected shape. This eliminates free-text wrapping and reduces parse failures.

```python
response_format={
    "type": "json_schema",
    "json_schema": {
        "name": "email_reply",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "The full email reply body"
                },
                "recipient": {
                    "type": "string",
                    "description": "Email address of the recipient"
                }
            },
            "required": ["reply", "recipient"],
            "additionalProperties": False
        }
    }
}
```

The JSON parse step (`json.loads`) is still required as the API returns the schema output as a JSON string in `content`.

---

## Integration with Agent

`agent.py` controls the full conversational flow. `generate_reply` is one step within it.

The agent's responsibilities around this tool:

1. Receive `EmailData` from `search_email`.
2. Display the email fields (`from_`, `subject`, `body`) to the user via `print()`.
3. Print a transitional message (e.g. `"Let me draft a response for you."`).
4. Call `generate_reply(email.body, email.from_, config)`.
5. Catch `OpenAIError` — print a user-facing message and exit if raised.
6. Display `result.reply` and `result.recipient` to the user.
7. Prompt the user: approve / reject / modify.
8. On modify: collect feedback string, call `generate_reply(email.body, email.from_, config, feedback=user_feedback)`, repeat from step 6.

The full conversational sequence this enables:

```
Agent: "I found an email from john@example.com — [subject and body shown]"
Agent: "Let me draft a response for you."
       → agent calls generate_reply(email.body, email.from_, config)
Agent: "Here's my suggested reply (to: john@example.com):"
       → agent prints result.reply
Agent: "Would you like me to send this reply?"
User:  "make it shorter and send it to mary@example.com instead"
       → agent calls generate_reply(email.body, email.from_, config, feedback="make it shorter and send it to mary@example.com instead")
Agent: "Here's the updated reply (to: mary@example.com):"
       → agent prints result.reply
Agent: "Would you like me to send this reply?"
User:  "yes"
       → agent calls send_email(result.reply, email.thread_id, config)
Agent: "Reply sent successfully."
```

Agent call site reference (do not implement `agent.py` in this task):

```python
# First generation
try:
    result = generate_reply(email.body, email.from_, config)
except OpenAIError as e:
    logger.error("OpenAI generation failed: %s", e)
    print("Failed to generate a reply. Please try again.")
    return

print(f"To: {result.recipient}")
print(result.reply)

# Revision after user feedback
try:
    result = generate_reply(email.body, email.from_, config, feedback=user_feedback)
except OpenAIError as e:
    logger.error("OpenAI revision failed: %s", e)
    print("Failed to revise the reply. Please try again.")
    return
```

---

## Implementation Steps

1. **Validate input** — at the top of the function, before any other logic:
   - If `email_content` is not a `str` or is empty/whitespace-only, raise `ValueError("email_content must be a non-empty string")`.
   - If `from_` is not a `str` or is empty/whitespace-only, raise `ValueError("from_ must be a non-empty string")`.
   - `feedback` requires no validation — `""` is valid and means first generation.

2. **Create a module-level logger**:
   ```python
   logger = logging.getLogger(__name__)
   ```

3. **Instantiate the OpenAI client**:
   ```python
   client = openai.OpenAI(api_key=config.openai_api_key)
   ```
   Do not call `os.environ` directly inside this function.

4. **Build the user message** based on whether `feedback` is provided:
   ```python
   if feedback.strip():
       user_message = (
           f"Original email:\n{email_content}\n\n"
           f"Sender: {from_}\n\n"
           f"User feedback:\n{feedback}"
       )
   else:
       user_message = f"Original email:\n{email_content}\n\nSender: {from_}"
   ```

5. **Build the message list**:
   ```python
   messages = [
       {"role": "system", "content": SYSTEM_PROMPT},
       {"role": "user", "content": user_message},
   ]
   ```
   Where `SYSTEM_PROMPT` is the module-level constant defined in the Prompt Design section.

6. **Call the API with Structured Outputs inside a `try/except` block**:
   ```python
   try:
       response = client.chat.completions.create(
           model=config.openai_model,
           messages=messages,
           response_format={
               "type": "json_schema",
               "json_schema": {
                   "name": "email_reply",
                   "strict": True,
                   "schema": {
                       "type": "object",
                       "properties": {
                           "reply": {"type": "string", "description": "The full email reply body"},
                           "recipient": {"type": "string", "description": "Email address of the recipient"},
                       },
                       "required": ["reply", "recipient"],
                       "additionalProperties": False,
                   },
               },
           },
       )
   except openai.OpenAIError as e:
       logger.error("OpenAI API call failed: %s", e)
       raise OpenAIError(str(e))
   ```

7. **Extract raw content**:
   ```python
   content = response.choices[0].message.content
   ```
   If `content` is `None` or empty, raise `OpenAIError("OpenAI returned an empty response")`.

8. **Parse the JSON response**:
   ```python
   try:
       data = json.loads(content)
       reply = data["reply"]
       recipient = data["recipient"]
   except (json.JSONDecodeError, KeyError) as e:
       logger.error("Failed to parse OpenAI response: %s", e)
       raise OpenAIError(f"OpenAI returned malformed JSON: {e}")
   ```

9. **Validate parsed values** — if `reply` or `recipient` is not a non-empty string, raise `OpenAIError("OpenAI returned incomplete structured output")`.

10. **Log and return**:
    ```python
    logger.debug("generate_reply: recipient=%s, reply_length=%d", recipient, len(reply))
    return ReplyResult(reply=reply, recipient=recipient)
    ```

---

## Error Handling

| Scenario | Required behavior |
|---|---|
| `email_content` is `""` or whitespace-only | Raise `ValueError("email_content must be a non-empty string")` |
| `email_content` is not a `str` | Raise `ValueError("email_content must be a non-empty string")` |
| `from_` is `""` or whitespace-only | Raise `ValueError("from_ must be a non-empty string")` |
| `from_` is not a `str` | Raise `ValueError("from_ must be a non-empty string")` |
| `feedback` is `""` or not provided | Treat as first generation — no special handling needed |
| `feedback` is whitespace-only | Treat as empty — use first-generation prompt |
| `OPENAI_API_KEY` missing | Already caught by `load_config()` — do not re-check here |
| `openai.AuthenticationError` | Catch as `openai.OpenAIError`, raise `OpenAIError(str(e))` |
| `openai.RateLimitError` | Catch as `openai.OpenAIError`, raise `OpenAIError(str(e))` |
| `openai.APIConnectionError` | Catch as `openai.OpenAIError`, raise `OpenAIError(str(e))` |
| Any other `openai.OpenAIError` subclass | Catch and raise `OpenAIError(str(e))` |
| Response `content` is `None` or `""` | Raise `OpenAIError("OpenAI returned an empty response")` |
| Response is not valid JSON | Catch `json.JSONDecodeError`, raise `OpenAIError(f"OpenAI returned malformed JSON: {e}")` |
| JSON missing `"reply"` or `"recipient"` key | Catch `KeyError`, raise `OpenAIError(f"OpenAI returned malformed JSON: {e}")` |
| `reply` or `recipient` is empty after parsing | Raise `OpenAIError("OpenAI returned incomplete structured output")` |

Use a single `except openai.OpenAIError as e` block for all SDK errors. Always raise the project's `OpenAIError` from `models.py`. Do not add retry logic.

---

## Files to Modify

| File | Action |
|---|---|
| `models.py` | Add `ReplyResult` dataclass |
| `tools/openai_generate.py` | Replace stub with full implementation |

No other files should be changed in this task. `agent.py` and `main.py` are out of scope.

---

## Acceptance Criteria

- [ ] `generate_reply(email_content, from_, config)` returns a `ReplyResult` with non-empty `reply` and `recipient` fields.
- [ ] `result.recipient` equals `from_` when no feedback is given.
- [ ] `generate_reply(email_content, from_, config, feedback="...")` returns a revised `ReplyResult`.
- [ ] When feedback contains an alternative address, `result.recipient` reflects that address.
- [ ] When `feedback` is `""` or whitespace-only, the first-generation user message template is used.
- [ ] When `feedback` is non-empty, the user message contains `"Original email:"`, `"Sender:"`, and `"User feedback:"` sections.
- [ ] The system prompt is identical in both modes and instructs JSON-only output.
- [ ] Malformed or missing JSON from the API raises `OpenAIError`.
- [ ] Passing `""` or whitespace as `email_content` raises `ValueError`.
- [ ] Passing `""` or whitespace as `from_` raises `ValueError`.
- [ ] Any `openai.OpenAIError` is caught and re-raised as the project's `OpenAIError`.
- [ ] `ReplyResult` is defined in `models.py` and imported by `tools/openai_generate.py`.
- [ ] The model used is `config.openai_model` — not hardcoded.
- [ ] `OPENAI_API_KEY` is never read from `os.environ` directly inside this function.
- [ ] No credentials or full email bodies are logged at `INFO` or above.
- [ ] The function body is ≤40 lines of logic (excluding docstring and blank lines).

---

## Example Usage

### Input email

```
Hi Sarah,

Just following up on the project proposal we discussed last Tuesday.
Could you send over the revised budget breakdown when you have a moment?

Thanks,
John
```

Sender: `john@example.com`

### First generation (no feedback)

```python
from config import load_config
from tools.openai_generate import generate_reply

config = load_config()
result = generate_reply(email_body, "john@example.com", config)

print(f"To: {result.recipient}")   # To: john@example.com
print(result.reply)
```

Expected output:

```
To: john@example.com

Hi John,

Thank you for following up. I'll send over the revised budget breakdown shortly.

Best regards,
Sarah
```

### Revision with alternative recipient

```python
result = generate_reply(
    email_body,
    "john@example.com",
    config,
    feedback="Make it shorter and send it to mary@example.com instead.",
)

print(f"To: {result.recipient}")   # To: mary@example.com
print(result.reply)
```

Expected output:

```
To: mary@example.com

Hi Mary,

I'll send the revised budget breakdown shortly.

Best regards,
Sarah
```

The agent receives the `ReplyResult`, displays both fields to the user, and asks for approval.

---

## Out of Scope for This Task

- `agent.py` — conversational orchestration and user approval flow (future task)
- `tools/gmail_send.py` — sending the approved reply (future task)
- Updating `main.py` beyond its current state from Task-001
- Retry logic, streaming, or multi-turn generation
