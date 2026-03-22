# Architecture

## System Overview

A single-loop Python agent that accepts a subject query, searches Gmail, generates a reply via OpenAI, presents it to the user for approval, and sends it if approved. No web server. No framework. CLI-driven.

---

## Module Structure

```
email_agent/
├── main.py              # Entry point. Runs the agent loop.
├── agent.py             # Agent logic. Orchestrates tool calls and user interaction.
├── tools/
│   ├── __init__.py
│   ├── gmail_search.py  # search_email(subject) → EmailData
│   ├── gmail_send.py    # send_email(reply, thread_id) → SendResult
│   └── openai_generate.py  # generate_reply(email_content) → str
├── models.py            # Shared data models (dataclasses or TypedDict)
├── config.py            # Loads credentials from environment variables only
└── requirements.txt
```

No subdirectory nesting beyond `tools/`. No shared utilities file unless strictly required.

---

## Agent Loop

```
1. Accept user input (email subject string)
2. Call search_email(subject)
   → If not found: print error, exit
3. Display email (from, subject, body) to user
4. Call generate_reply(email_content)
   → If API failure: print error, exit
5. Display generated reply to user
6. Prompt user: [approve / reject / modify]
   - approve  → call send_email(reply, thread_id)
   - reject   → exit without sending
   - modify   → accept new reply text from user, repeat step 6
7. Display send result
8. Exit
```

The loop runs once per invocation. It does NOT retry automatically on user rejection.

---

## Tool Abstraction

Each tool is a standalone function in its own module. Tools:
- Accept plain Python types or model instances as inputs
- Return typed model instances (defined in `models.py`)
- Raise specific exceptions on failure (do NOT return error strings)
- Have no knowledge of each other

The agent (`agent.py`) is the only layer that calls tools. `main.py` only starts the agent.

---

## Data Flow

```
main.py
  └─→ agent.run(subject)
        ├─→ gmail_search.search_email(subject)      → EmailData
        ├─→ [display to user]
        ├─→ openai_generate.generate_reply(email)   → str
        ├─→ [display to user, await approval]
        └─→ gmail_send.send_email(reply, thread_id) → SendResult
```

No data is passed between tools directly. All state lives in `agent.py` local variables during a single run.

---

## Credentials

All credentials are loaded in `config.py` from environment variables. `config.py` exports a single `Config` object consumed by tools. No tool reads environment variables directly.

---

## Error Handling Strategy

- Tools raise typed exceptions.
- `agent.py` catches exceptions at each tool call site and handles them (log + exit or prompt user).
- `main.py` wraps `agent.run()` in a top-level try/except to catch unhandled errors.
