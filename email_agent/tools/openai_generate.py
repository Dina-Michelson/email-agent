"""OpenAI generate tool — generates a professional email reply via OpenAI API."""
import json
import logging

import openai

from config import Config
from models import OpenAIError, ReplyResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a professional assistant that writes clear, polite, and concise "
    "email replies. The recipient should normally be the sender of the original "
    "email unless the user explicitly requests a different recipient."
)


def generate_reply(
    email_content: str,
    from_: str,
    config: Config,
    user_email: str = "",
    user_name: str = "",
    feedback: str = "",
) -> ReplyResult:
    if not isinstance(email_content, str) or not email_content.strip():
        raise ValueError("email_content must be a non-empty string")
    if not isinstance(from_, str) or not from_.strip():
        raise ValueError("from_ must be a non-empty string")

    client = openai.OpenAI(api_key=config.openai_api_key)

    if user_name.strip() and user_email.strip():
        author_line = f"{user_name} <{user_email}>"
    elif user_name.strip():
        author_line = user_name
    elif user_email.strip():
        author_line = user_email
    else:
        author_line = "You"

    if feedback.strip():
        user_message = (
            f"Original email:\n{email_content}\n\n"
            f"Sender: {from_}\n"
            f"Author of the reply: {author_line}\n\n"
            f"User feedback:\n{feedback}"
        )
    else:
        user_message = (
            f"Original email:\n{email_content}\n\n"
            f"Sender: {from_}\n"
            f"Author of the reply: {author_line}"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

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
        )
    except openai.OpenAIError as e:
        logger.error("OpenAI API call failed: %s", e)
        raise OpenAIError(str(e))

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise OpenAIError("OpenAI returned an empty response")

    try:
        data = json.loads(content)
        reply = data["reply"]
        recipient = data["recipient"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse OpenAI response: %s", e)
        raise OpenAIError(f"OpenAI returned malformed JSON: {e}")

    if not reply.strip() or not recipient.strip():
        raise OpenAIError("OpenAI returned incomplete structured output")

    logger.debug(
        "generate_reply: recipient=%s, reply_length=%d",
        recipient,
        len(reply)
    )

    return ReplyResult(reply=reply, recipient=recipient)

