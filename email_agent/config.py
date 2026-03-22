import os
from dataclasses import dataclass


@dataclass
class Config:
    gmail_credentials_path: str
    gmail_token_path: str
    openai_api_key: str
    openai_model: str


def load_config() -> Config:
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    return Config(
        gmail_credentials_path=os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        gmail_token_path=os.environ.get("GMAIL_TOKEN_PATH", "token.json"),
        openai_api_key=openai_api_key,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
    )
