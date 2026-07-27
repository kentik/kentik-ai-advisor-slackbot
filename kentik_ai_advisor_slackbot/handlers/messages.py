import logging
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx
from kentik_ai_advisor_slackbot.slack_messages import resolve_mentions

logger = logging.getLogger(__name__)


@ctx.app.event("message")
async def handle_message(event: dict[str, Any], client: AsyncWebClient):
    """Handle direct messages to the bot.

    Args:
        event: Slack event data
        client: Slack AsyncWebClient
    """
    logger.info(f"received message event: {event.get('type')}")
    logger.debug(f"full event: {event}")

    if "thread_ts" in event:
        # Ignore threaded messages here, they are handled by the assistant
        logger.info("ignore message in thread, handled by assistant")
        return

    # Only handle direct messages (DMs)
    channel_type = event.get("channel_type")
    if channel_type != "im":
        return

    # Ignore bot messages
    if event.get("subtype") == "bot_message":
        return

    text = event.get("text", "").strip()
    channel_id = event.get("channel")
    user_id = event.get("user")

    if not text:
        return

    logger.info(f"processing message from user {user_id} in channel {channel_id}")

    bot_user_id = await ctx.engine.get_bot_user_id(client)
    question = await resolve_mentions(client, text, bot_user_id)

    # Handle as new conversation (no threading in DMs)
    await ctx.engine.handle_question(
        client=client,
        channel_id=channel_id,
        thread_ts=None,
        question=question,
        event_ts=event.get("ts"),
    )
