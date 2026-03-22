import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from config import load_config
from models import EmailNotFoundError, GmailAPIError, OpenAIError
from tools.gmail_search import get_user_profile, search_email
from tools.openai_generate import generate_reply

log_level = os.environ.get("LOG_LEVEL", "DEBUG")
logging.basicConfig(level=getattr(logging, log_level, logging.DEBUG))
logger = logging.getLogger(__name__)

try:
    config = load_config()
except EnvironmentError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)

try:
    user_email, user_name = get_user_profile(config)
    logger.info("Authenticated as: %s (%s)", user_email, user_name or "no display name")
except GmailAPIError as e:
    print(f"Gmail error: {e}")
    sys.exit(1)

subject = input("Enter email subject to search: ").strip()

try:
    email = search_email(subject, config)
except EmailNotFoundError as e:
    print(str(e))
    sys.exit(0)
except GmailAPIError as e:
    print(f"Gmail error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)

print(f"From: {email.from_}")
print(f"Subject: {email.subject}")
print(f"Date: {email.date}")
print(f"Body:\n{email.body}")

print("\nGenerating reply...")
try:
    result = generate_reply(email.body, email.from_, config, user_email=user_email, user_name=user_name)
except OpenAIError as e:
    print(f"OpenAI error: {e}")
    sys.exit(1)

print(f"\nTo: {result.recipient}")
print(f"Reply:\n{result.reply}")

feedback = input("\nFeedback to revise (or press Enter to skip): ").strip()
if feedback:
    try:
        result = generate_reply(email.body, email.from_, config, user_email=user_email, user_name=user_name, feedback=feedback)
    except OpenAIError as e:
        print(f"OpenAI error: {e}")
        sys.exit(1)
    print(f"\nTo: {result.recipient}")
    print(f"Revised reply:\n{result.reply}")
