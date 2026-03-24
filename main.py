import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from config import load_config
from agent import run

log_level = os.environ.get("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))

try:
    config = load_config()
except EnvironmentError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)

run(config)
