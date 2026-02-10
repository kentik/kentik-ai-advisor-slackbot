"""Main Kentik AI Advisor Slackbot application."""

import asyncio

from slack_bolt.async_app import AsyncApp, AsyncAssistant

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler


from kentik_ai_advisor_slackbot.context import SlackContext
from kentik_ai_advisor_slackbot.query_engine import QueryEngine
from .ai_advisor_client import AIAdvisorClient
from .config import (
    CONVERSATIONS_DB_PATH,
    KENTIK_API_EMAIL,
    KENTIK_API_TOKEN,
    KENTIK_API_URL,
    POLLING_INTERVAL_SECONDS,
    POLLING_TIMEOUT_SECONDS,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    logger,
)
from .conversation_store import ConversationStore

# Initialize components
app = AsyncApp(token=SLACK_BOT_TOKEN)
ai_advisor = AIAdvisorClient(
    api_url=KENTIK_API_URL,
    api_email=KENTIK_API_EMAIL,
    api_token=KENTIK_API_TOKEN,
    poll_interval=POLLING_INTERVAL_SECONDS,
    timeout=POLLING_TIMEOUT_SECONDS,
)
conversation_store = ConversationStore(db_path=CONVERSATIONS_DB_PATH)
assistant = AsyncAssistant()

ctx = SlackContext(
    app=app,
    assistant=assistant,
    advisor=ai_advisor,
    store=conversation_store,
    engine=QueryEngine(advisor_client=ai_advisor, store=conversation_store),
)

app.use(assistant)


async def async_main():
    """Start the Slackbot application (async)."""
    logger.info("starting AI Advisor Slackbot...")
    logger.info(f"Kentik API URL: {KENTIK_API_URL}")
    logger.info("connecting to Slack via Socket Mode...")

    from kentik_ai_advisor_slackbot import handlers  # noqa: F401 - register handlers

    try:
        handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
        logger.info("✓ Socket Mode handler created successfully")
        logger.info("✓ Bot is now listening for events...")
        logger.info("  - Listening for @mentions in channels")
        logger.info("  - Listening for direct messages")
        logger.info("  - Listening for assistant threads")
        await handler.start_async()
    except Exception as e:
        logger.error(f"failed to start bot: {e}")
        raise
    finally:
        await ai_advisor.close()


def main():
    """Entry point for the Slackbot application."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
