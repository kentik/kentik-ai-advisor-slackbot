import logging
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx
from kentik_ai_advisor_slackbot.slack_messages import post_message, resolve_mentions

logger = logging.getLogger(__name__)

@ctx.app.event("reaction_added")
async def handle_reaction_added_events(event: dict[str, Any], client: AsyncWebClient):
    logger.info(event)

@ctx.app.event("app_mention")
async def handle_app_mention(event: dict[str, Any], client: AsyncWebClient):
    """Handle @mentions of the bot.

    Args:
        event: Slack event data
        client: Slack AsyncWebClient
    """
    logger.info(f"received app_mention event: {event.get('type')}")
    logger.debug(f"full event: {event}")

    text = event.get("text", "").strip()
    user_id = event.get("user")
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts")  # None if in main channel
    event_ts = event.get("ts")

    logger.info(f"processing mention from user {user_id} in channel {channel_id}")

    # Remove the bot's own mention; resolve any other mentioned user to their email
    bot_user_id = await ctx.engine.get_bot_user_id(client)
    question = await resolve_mentions(client, text, bot_user_id)

    if not question:
        help_text = (
            "Hello! I'm the Kentik AI Advisor bot. "
            "Mention me with a question about your network and I'll help you analyze it.\n\n"
            "Example: `@kentik show me top talkers in the last hour`"
        )
        await post_message(client, channel_id, help_text, thread_ts or event_ts)
        return

    # If not in a thread, use event timestamp as the thread parent
    if not thread_ts:
        thread_ts = event_ts
    
    await ctx.engine.handle_question(
        client=client,
        channel_id=channel_id,
        thread_ts=thread_ts,
        question=question,
        event_ts=event_ts,
    )
