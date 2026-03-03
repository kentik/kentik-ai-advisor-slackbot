"""Configuration loading and validation for the Kentik AI Advisor Slackbot."""

import logging
import os

from dotenv import load_dotenv

load_dotenv(override=True)


def _get_env(key: str, default: str | None = None) -> str:
    """Get environment variable with optional default, stripping quotes."""
    value = os.getenv(key, default)
    if value is None:
        return ""
    return value.strip("'\"")


def _get_env_int(key: str, default: str) -> int:
    """Get environment variable as integer."""
    return int(_get_env(key, default))


# Slack configuration
SLACK_BOT_TOKEN = _get_env("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = _get_env("SLACK_APP_TOKEN")

# Kentik API configuration
KENTIK_API_URL = _get_env("KENTIK_API_URL")
KENTIK_API_EMAIL = _get_env("KENTIK_API_EMAIL")
KENTIK_API_TOKEN = _get_env("KENTIK_API_TOKEN")

# Application settings
THREAD_CONTEXT_MESSAGES = _get_env_int("THREAD_CONTEXT_MESSAGES", "20")
POLLING_TIMEOUT_SECONDS = _get_env_int("POLLING_TIMEOUT_SECONDS", "120")
POLLING_INTERVAL_SECONDS = _get_env_int("POLLING_INTERVAL_SECONDS", "2")
CONVERSATIONS_DB_PATH = _get_env("CONVERSATIONS_DB_PATH", "conversations.db")


def validate_config() -> None:
    """Validate that all required environment variables are set.

    Raises:
        EnvironmentError: If any required variable is missing.
    """
    required = [
        SLACK_BOT_TOKEN,
        SLACK_APP_TOKEN,
        KENTIK_API_URL,
        KENTIK_API_EMAIL,
        KENTIK_API_TOKEN,
    ]
    if not all(required):
        raise EnvironmentError(
            "Required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, "
            "KENTIK_API_URL, KENTIK_API_EMAIL, KENTIK_API_TOKEN"
        )


def setup_logging() -> logging.Logger:
    """Configure and return the application logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("kentik-ai-advisor-slackbot")


# Validate on import
validate_config()

# Setup logger
logger = setup_logging()
