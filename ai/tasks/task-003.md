# Task 003 — Conversation Agent

## Objective

Implement `agent.py` — a true agentic LLM loop that receives user input, maintains a full conversation history, and lets the LLM decide at every turn whether to call a tool or respond directly.

The agent does not make flow decisions in Python code. All decisions (what tool to call, when to reply, when to stop) are made by the LLM based on the conversation history it receives.

---

## Architecture

```
main.py
  └── agent.run()
        └── [while True] — get user input
              └── [inner loop] — LLM decides next action
                    ├── tool call → execute → append result → LLM continues
                    ├── tool call → execute → append result → LLM continues
                    └── text response → print → wait for next user input
```

The inner loop keeps running as long as the LLM returns tool calls. It only breaks when the LLM responds in plain text. The outer loop then waits for the next user message.

---

## Core Design Principle

At every turn:

1. Append the user message to `messages`.
2. Call the LLM with the full `messages` list and all available tools.
3. If the LLM returns tool calls:
   - Execute each tool.
   - Append the assistant tool-call message and each tool result to `messages`.
   - Go back to step 2 — the LLM sees the results and decides what to do next.
4. If the LLM returns a text response:
   - Print it.
   - Append it to `messages`.
   - Break the inner loop and wait for the next user input.

**Python code never decides which tool to call or what phase the conversation is in.** The LLM infers context from the full message history.

---

## Execution State

A small `ExecState` dataclass holds Python objects needed to execute tools. It is **not** used for flow control — the LLM drives the flow.

```python
@dataclass
class ExecState:
    email: EmailData | None = None   # result of last search_email call
    reply: str = ""                  # result of last generate_reply call
    recipient: str = ""              # recipient resolved by generate_reply
    sender_name: str = ""            # display name from get_user_profile
    sender_email: str = ""           # email address from get_user_profile
```

---

## Tools

All three tools are defined upfront and always passed to every LLM call. The LLM decides which to call based on context.

### `search_email`

| Parameter | Type | Description |
|---|---|---|
| `subject` | `string` | Subject or topic of the email to find |

Calls `search_email(subject, config)` from `tools/gmail_search.py`.
Returns a text summary of the found email (from, date, subject, body) that goes into the message history as a tool result.
On failure, returns an error string — the LLM reads it and responds to the user accordingly.

### `generate_reply`

| Parameter | Type | Description |
|---|---|---|
| `feedback` | `string` | Modification instructions. Empty string for first draft. |

Calls `generate_reply(email.body, email.from_, config, ..., feedback=feedback)`.
Returns a text summary with the recipient and draft body.
Fails gracefully if no email has been found yet (returns an error string).

### `send_email`

No parameters. Uses `ExecState.email` and `ExecState.reply`.
Calls `send_reply(state.email, state.reply, config)` from `tools/gmail_send.py`.
Returns a confirmation string or error string.

---

## System Prompt

```python
SYSTEM_PROMPT = (
    "You are a conversational email reply assistant. "
    "You help the user find emails and draft, refine, and send replies.\n\n"
    "Available tools:\n"
    "- search_email: search Gmail for an email by subject or topic.\n"
    "  Call this when the user mentions an email they want to reply to.\n"
    "- generate_reply: draft or revise a reply to the found email.\n"
    "  Call this after finding an email, or when the user asks to change the draft.\n"
    "  Pass the user's modification instructions as 'feedback'. "
    "  Leave feedback empty for the first draft.\n"
    "- send_email: send the current reply draft.\n"
    "  Call this only after the user explicitly approves sending.\n\n"
    "Always confirm with the user before sending. "
    "After sending, ask if they need anything else."
)
```

The system message is the first entry in `messages` and persists for the entire conversation.

---

## Implementation Steps

### Step 1 — Replace `main.py`

```python
import logging
import sys

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from config import load_config
from agent import run

logging.basicConfig(level=logging.WARNING)

try:
    config = load_config()
except EnvironmentError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)

run(config)
```

### Step 2 — Define `ExecState`

```python
@dataclass
class ExecState:
    email: EmailData | None = None
    reply: str = ""
    recipient: str = ""
    sender_name: str = ""
    sender_email: str = ""
```

### Step 3 — Define `ALL_TOOLS`

A module-level list with all three tool definitions (see Tools section above).

### Step 4 — Implement tool executor functions

```python
def _exec_search_email(subject: str, state: ExecState, config: Config) -> str:
    try:
        state.email = search_email(subject, config)
    except EmailNotFoundError:
        return f'No email found matching "{subject}". Ask the user to try a different subject.'
    except GmailAPIError as e:
        logger.error("Gmail search failed: %s", e)
        return f"Gmail search failed: {e}"
    email = state.email
    return (
        f"Email found.\n"
        f"From: {email.from_}\nDate: {email.date}\n"
        f"Subject: {email.subject}\nBody:\n{email.body}"
    )


def _exec_generate_reply(feedback: str, state: ExecState, config: Config) -> str:
    if state.email is None:
        return "No email has been found yet. Search for an email first."
    if not state.sender_name and not state.sender_email:
        try:
            state.sender_email, state.sender_name = get_user_profile(config)
        except GmailAPIError:
            pass
    try:
        result = generate_reply(
            state.email.body,
            state.email.from_,
            config,
            user_email=state.sender_email,
            user_name=state.sender_name,
            feedback=feedback,
        )
    except OpenAIError as e:
        logger.error("generate_reply failed: %s", e)
        return f"Failed to generate reply: {e}"
    state.reply = result.reply
    state.recipient = result.recipient
    return (
        f"Reply drafted.\nTo: {result.recipient}\n---\n{result.reply}\n---"
    )


def _exec_send_email(state: ExecState, config: Config) -> str:
    if not state.reply:
        return "No reply has been drafted yet."
    if state.email is None:
        return "No email context available."
    try:
        from tools.gmail_send import send_reply
        result = send_reply(state.email, state.reply, config)
        if result.success:
            return f"Reply sent successfully to {state.recipient}."
        return "Send failed — the email was not delivered."
    except (ImportError, NotImplementedError):
        return f"[Stub] Would send reply to {state.recipient}. GmailSendTool not yet implemented."
    except (GmailAPIError, SendFailedError) as e:
        logger.error("Send failed: %s", e)
        return f"Send failed: {e}"
    except Exception as e:
        logger.error("Send failed unexpectedly: %s", e)
        return f"Send failed: {e}"
```

### Step 5 — Implement `_execute_tool`

Dispatches a single tool call to the correct executor. Returns the result as a string.

```python
def _execute_tool(call, state: ExecState, config: Config) -> str:
    name = call.function.name
    try:
        args = json.loads(call.function.arguments)
    except json.JSONDecodeError as e:
        return f"Bad tool arguments: {e}"

    logger.debug("Executing tool=%s args=%s", name, args)

    if name == "search_email":
        return _exec_search_email(args.get("subject", ""), state, config)
    if name == "generate_reply":
        return _exec_generate_reply(args.get("feedback", ""), state, config)
    if name == "send_email":
        return _exec_send_email(state, config)
    return f"Unknown tool: {name}"
```

### Step 6 — Implement `_llm_call`

A thin wrapper around the OpenAI chat completions call. Raises `OpenAIError` on failure.

```python
def _llm_call(messages: list, config: Config):
    client = openai.OpenAI(api_key=config.openai_api_key)
    try:
        response = client.chat.completions.create(
            model=config.openai_model,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
        )
    except openai.OpenAIError as e:
        logger.error("LLM call failed: %s", e)
        raise OpenAIError(str(e))
    return response.choices[0].message
```

### Step 7 — Implement `run(config: Config) -> None`

The outer loop collects user input. The inner loop runs until the LLM gives a text response.

```python
def run(config: Config) -> None:
    state = ExecState()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("Hello! I can help you respond to emails.")
    print('What would you like help with? (or type "quit" to exit)\n')

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})

        # Inner agentic loop — runs until LLM gives a text response
        while True:
            try:
                message = _llm_call(messages, config)
            except OpenAIError:
                print("Something went wrong. Please try again.")
                messages.pop()  # remove user message so the turn can be retried
                break

            if not message.tool_calls:
                # LLM decided to respond — print and wait for next user input
                text = message.content or ""
                if text:
                    print(text)
                messages.append({"role": "assistant", "content": text})
                break

            # LLM chose tools — append its decision to history
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # Execute each tool and append results to history
            for call in message.tool_calls:
                _announce_tool(call)
                result = _execute_tool(call, state, config)
                logger.debug("tool=%s result_preview=%s", call.function.name, result[:120])
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

            # Loop — LLM sees tool results and decides what to do next
```

### Step 8 — Implement `_announce_tool`

Prints a brief status line while a tool runs, so the user is not left staring at a blank prompt.

```python
def _announce_tool(call) -> None:
    try:
        args = json.loads(call.function.arguments)
    except json.JSONDecodeError:
        args = {}
    name = call.function.name
    if name == "search_email":
        print(f'Searching for email about: "{args.get("subject", "")}"...')
    elif name == "generate_reply":
        print("Updating the reply..." if args.get("feedback") else "Drafting a reply...")
    elif name == "send_email":
        print("Sending reply...")
```

---

## Error Handling

All error handling flows through the tool result strings. When a tool fails, it returns a human-readable error string. The LLM reads that string as a tool result and decides how to respond to the user. Python code does not catch tool errors and print them directly — that is the LLM's job.

| Scenario | Behavior |
|---|---|
| `search_email` finds nothing | Tool returns error string → LLM tells user and offers to try again |
| `GmailAPIError` during search | Tool returns error string → LLM reports to user |
| `generate_reply` called before search | Tool returns error string → LLM asks user to search first |
| `OpenAIError` from `generate_reply` | Tool returns error string → LLM reports to user |
| `send_email` called before draft | Tool returns error string → LLM asks user to draft first |
| `send_reply` not yet implemented | Tool returns stub string → LLM reports to user |
| `OpenAIError` from `_llm_call` | Print user-facing message, remove last user message, break inner loop |
| `KeyboardInterrupt` or `EOFError` | Print "Goodbye." and exit cleanly |

---

## Logging

- `logger = logging.getLogger(__name__)` at module level.
- Log all tool calls at `DEBUG` with name and args.
- Log tool result previews at `DEBUG` (first 120 chars).
- Log all caught exceptions at `ERROR`.
- Never log email body content, API keys, or OAuth tokens at `INFO` or above.

---

## Files to Modify

| File | Action |
|---|---|
| `agent.py` | Replace stub with full implementation |
| `main.py` | Replace Task-001 scaffolding with entry point shown in Step 1 |

---

## Acceptance Criteria

- [ ] `python main.py` starts a conversation loop.
- [ ] At every turn, the LLM receives the full `messages` list including all prior tool calls and results.
- [ ] All three tools (`search_email`, `generate_reply`, `send_email`) are always passed to every LLM call.
- [ ] Python code does not decide which tool to call — only the LLM does.
- [ ] When the LLM returns tool calls, they are executed and appended to `messages` before the LLM is called again.
- [ ] The inner loop continues until the LLM returns a plain-text response.
- [ ] Tool errors are returned as strings in tool results — the LLM decides how to communicate them.
- [ ] `send_email` is only called when the LLM chooses to call it (i.e. when the user has approved).
- [ ] The LLM can chain multiple tool calls in one turn (e.g. search then generate without user intervention).
- [ ] `KeyboardInterrupt` exits cleanly.
- [ ] `run()` never raises an unhandled exception.
- [ ] No credentials, email bodies, or API keys appear in logs at `INFO` or above.

---

## Example Interaction

```
Hello! I can help you respond to emails.
What would you like help with? (or type "quit" to exit)

> Can you help me respond to the email about the project proposal follow-up?
Searching for email about: "project proposal follow-up"...
Drafting a reply...
I found an email from john@example.com (Subject: Project proposal follow-up).

Here's a suggested reply:

To: john@example.com
---
Hi John,

Thank you for following up. I'll review the proposal and get back to you by end of week.

Best regards,
Sarah
---

Would you like me to send this, or would you like any changes?

> Can you make it shorter?
Updating the reply...
Here's the updated version:

To: john@example.com
---
Hi John, thanks for the nudge — I'll get back to you by end of week.

Best regards,
Sarah
---

Shall I send this?

> Yes, send it
Sending reply...
Done! The reply has been sent to john@example.com. Is there anything else I can help you with?
```

---

## Out of Scope for This Task

- `tools/gmail_send.py` full implementation (already stubbed; Task-004)
- Parallel tool calls (LLM may call one tool at a time)
- Streaming responses
- Persisting conversation history across program runs
