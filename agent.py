"""Conversation agent — agentic LLM loop that decides tool calls from conversation history."""
import json
import logging
import re
from dataclasses import dataclass

import openai

from config import Config
from models import (
    EmailData,
    EmailNotFoundError,
    GmailAPIError,
    OpenAIError,
    SendFailedError,
)
from tools.gmail_search import get_user_profile, search_email
from tools.openai_generate import generate_reply

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a conversational email reply assistant. "
    "You help the user find emails and draft, refine, and send replies.\n\n"
    "Available tools:\n"
    "- search_email: search Gmail for an email by subject or topic.\n"
    "  Call this when the user mentions an email they want to reply to.\n"
    "- generate_reply: draft or revise a reply to the found email.\n"
    "  Call this after finding an email, or when the user asks to change the draft.\n"
    "  Pass the user's modification instructions as 'feedback'. "
    "Leave feedback empty for the first draft.\n"
    "- send_email: send the current reply draft.\n"
    "  Call this only after the user explicitly approves sending.\n"
    "  Pass recipient only when correcting the address after a delivery failure.\n\n"
    "IMPORTANT: After calling generate_reply, do NOT reproduce or paraphrase the draft "
    "in your text response. The draft is already displayed to the user. "
    "Just ask briefly if they would like to send it or make changes.\n\n"
    "DELIVERY FAILURES: After sending, if the tool result says a delivery failure was "
    "detected, inform the user clearly that the email may not have been delivered, "
    "and ask them to provide the correct email address. "
    "When they provide a corrected address, call send_email with that address as recipient.\n\n"
    "Always confirm with the user before sending. "
    "After sending successfully, ask if they need anything else."
)

# ---------------------------------------------------------------------------
# Tool definitions — always passed to every LLM call
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_email",
            "description": (
                "Search Gmail for an email by subject or topic. "
                "Call this when the user wants to reply to or find a specific email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "The subject or topic of the email to find.",
                    }
                },
                "required": ["subject"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_reply",
            "description": (
                "Draft or revise a reply to the email that was found. "
                "For the first draft pass an empty string for feedback. "
                "For revisions pass the user's modification instructions as feedback."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feedback": {
                        "type": "string",
                        "description": (
                            "Modification instructions from the user. "
                            "Empty string for first draft."
                        ),
                    }
                },
                "required": ["feedback"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": (
                "Send the current reply draft. "
                "Call this only when the user explicitly approves sending. "
                "recipient is only needed to correct the address after a delivery failure — "
                "otherwise the recipient from generate_reply is used."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Corrected recipient address. Only pass this after a delivery failure.",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Execution state — Python objects needed by tools, not flow control
# ---------------------------------------------------------------------------

@dataclass
class ExecState:
    email: EmailData | None = None
    reply: str = ""
    recipient: str = ""
    sender_name: str = ""
    sender_email: str = ""

# ---------------------------------------------------------------------------
# Tool executors — each returns a plain string that goes into message history
# ---------------------------------------------------------------------------

def _exec_search_email(args: dict, state: ExecState, config: Config) -> str:
    subject = args.get("subject", "")
    try:
        state.email = search_email(subject, config)
    except EmailNotFoundError:
        return f'No email found matching "{subject}". Ask the user to try a different subject.'
    except GmailAPIError as e:
        logger.error("Gmail search failed: %s", e)
        return f"Gmail search failed: {e}"
    e = state.email
    msgs = e.thread_messages if e.thread_messages else [{"from_": e.from_, "date": e.date, "body": e.body}]
    if len(msgs) > 1:
        thread_text = "\n\n".join(
            f"Message {i + 1} — From: {m['from_']}, Date: {m['date']}:\n{_sanitize(m['body'])}"
            for i, m in enumerate(msgs)
        )
        return f"Email thread found ({len(msgs)} messages).\nSubject: {e.subject}\n\n{thread_text}"
    return (
        f"Email found.\n"
        f"From: {e.from_}\nDate: {e.date}\nSubject: {e.subject}\nBody:\n{_sanitize(e.body)}"
    )


def _exec_generate_reply(args: dict, state: ExecState, config: Config) -> str:
    feedback = args.get("feedback", "")
    if state.email is None:
        return "No email has been found yet. Search for an email first."
    if not state.sender_name and not state.sender_email:
        try:
            state.sender_email, state.sender_name = get_user_profile(config)
        except GmailAPIError:
            pass

    # Build full thread text so the LLM has complete context
    msgs = state.email.thread_messages
    if msgs:
        thread_text = "\n\n".join(
            f"Message {i + 1} — From: {m['from_']}, Date: {m['date']}:\n{m['body']}"
            for i, m in enumerate(msgs)
        )
        # The "other party" is whichever address in the thread is not the authenticated user
        other_party = state.email.from_
        for m in reversed(msgs):
            if state.sender_email and state.sender_email not in m["from_"]:
                other_party = m["from_"]
                break
    else:
        thread_text = state.email.body
        other_party = state.email.from_

    try:
        result = generate_reply(
            thread_text,
            other_party,
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
    # Return only a brief summary — the full reply is already printed by _print_reply
    return f"Reply drafted. To: {result.recipient}"


def _exec_send_email(args: dict, state: ExecState, config: Config) -> str:
    recipient = args.get("recipient", "")
    if not state.reply:
        return "No reply has been drafted yet. Draft a reply first."
    if state.email is None:
        return "No email context available."
    if recipient:
        state.recipient = recipient.strip()
    import time
    sent_at = time.time()
    try:
        from tools.gmail_send import check_delivery_failure, send_reply
        result = send_reply(state.email, state.reply, config, recipient=state.recipient)
        if not result.success:
            return "Send failed — the email was not delivered."
    except (GmailAPIError, SendFailedError) as e:
        logger.error("Send failed: %s", e)
        return f"Send failed: {e}"
    except Exception as e:
        logger.error("Send failed unexpectedly: %s", e)
        return f"Send failed: {e}"

    # Email accepted by Gmail — now check for a bounce notification.
    print("Checking delivery status (this may take a few seconds)...")
    bounced = check_delivery_failure(config, sent_at=sent_at, recipient=state.recipient)
    if bounced:
        return (
            f"Reply sent to {state.recipient}, but a delivery failure notification was detected. "
            "The email address may be incorrect. "
            "Please ask the user to provide the correct email address."
        )
    return f"Reply sent successfully to {state.recipient}."


_TOOL_REGISTRY: dict = {
    "search_email": _exec_search_email,
    "generate_reply": _exec_generate_reply,
    "send_email": _exec_send_email,
}


def _execute_tool(call, state: ExecState, config: Config) -> str:
    name = call.function.name
    try:
        args = json.loads(call.function.arguments)
    except json.JSONDecodeError as e:
        return f"Bad tool arguments: {e}"

    logger.debug("Executing tool=%s args=%s", name, args)

    executor = _TOOL_REGISTRY.get(name)
    if executor is None:
        return f"Unknown tool: {name}"
    return executor(args, state, config)


def _format_body(body: str) -> str:
    """Render quoted reply chains with visual indentation instead of > markers."""
    lines = body.splitlines()
    out = []
    prev_depth = 0
    for line in lines:
        # Count and strip leading '>' markers
        depth = 0
        text = line
        while text.startswith(">"):
            depth += 1
            text = text[1:].lstrip()

        # Insert a separator header when entering a deeper quote level
        if depth > prev_depth:
            pad = "  " * depth
            out.append(f"\n{pad}┌─ earlier in thread {'─' * max(0, 44 - depth * 2)}")

        if depth == 0:
            out.append(text)
        else:
            pad = "  " * depth
            out.append(f"{pad}│ {text}" if text else f"{pad}│")

        prev_depth = depth

    return "\n".join(out)


def _print_email(e) -> None:
    width = 60
    msgs = e.thread_messages if e.thread_messages else [{"from_": e.from_, "date": e.date, "body": e.body}]
    print(f"\n{'─' * width}")
    print(f"  Subject: {e.subject}")
    if len(msgs) > 1:
        print(f"  Thread:  {len(msgs)} messages")
    print(f"{'─' * width}")
    for i, msg in enumerate(msgs):
        if len(msgs) > 1:
            print(f"\n  [{i + 1}/{len(msgs)}] From: {msg['from_']}  |  {msg['date']}")
            print(f"  {'·' * (width - 2)}")
        else:
            print(f"  From:    {msg['from_']}")
            print(f"  Date:    {msg['date']}")
            print()
        print(_format_body(msg["body"]))
    print(f"{'─' * width}\n")


def _print_reply(reply: str, recipient: str) -> None:
    width = 60
    print(f"\nAgent: Here is my suggested reply:")
    print(f"  To: {recipient}")
    print(f"{'─' * width}")
    print(reply)
    print(f"{'─' * width}\n")


def _announce_tool(call) -> None:
    """Print a brief status line so the user knows a tool is running."""
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


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")
_FAREWELL_PHRASES = ("goodbye", "have a great", "take care", "farewell", "good luck")


def _sanitize(text: str) -> str:
    """Strip control characters and lone surrogates that break JSON serialization."""
    text = _CONTROL_CHARS.sub("", text)
    text = _LONE_SURROGATE.sub("\ufffd", text)
    return text


def _is_farewell(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in _FAREWELL_PHRASES)

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(config: Config) -> None:
    state = ExecState()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    reset_on_next = False

    print("Hello! I am an AI agent can help you respond to emails.")
    print('What would you like help with? (or type "quit" to exit)\n')

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Goodbye.")
            break

        if reset_on_next:
            state = ExecState()
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            reset_on_next = False

        messages.append({"role": "user", "content": user_input})

        # Inner agentic loop — runs until the LLM gives a plain-text response.
        # The LLM decides which tools to call (if any) based on the full message history.
        while True:
            try:
                message = _llm_call(messages, config)
            except OpenAIError:
                print("Something went wrong. Please try again.")
                messages.pop()  # remove the user message so the turn can be retried
                break

            if not message.tool_calls:
                # LLM chose to respond — print and return to outer loop
                text = message.content or ""
                if text:
                    print(f"Agent: {text}")
                messages.append({"role": "assistant", "content": text})
                if _is_farewell(text):
                    reset_on_next = True
                break

            # LLM chose tools — record its decision in history
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

            # Execute each tool and append the result to history
            for call in message.tool_calls:
                _announce_tool(call)
                result = _execute_tool(call, state, config)
                logger.debug("tool=%s result_preview=%s", call.function.name, result[:120])
                if call.function.name == "search_email" and state.email is not None:
                    print(f"Agent: Found an email from {state.email.from_}:")
                    _print_email(state.email)
                elif call.function.name == "generate_reply" and state.reply:
                    _print_reply(state.reply, state.recipient)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

            # Continue inner loop — LLM sees tool results and decides what to do next
