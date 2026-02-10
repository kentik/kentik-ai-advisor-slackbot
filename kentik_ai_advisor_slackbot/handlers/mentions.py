import logging
import re
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx
from kentik_ai_advisor_slackbot.slack_messages import post_message

logger = logging.getLogger(__name__)


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

    # Remove bot mention from text
    question = re.sub(r"<@\w+>", "", text).strip()

    if not question:
        help_text = (
            "Hello! I'm the Kentik AI Advisor bot. "
            "Mention me with a question about your network and I'll help you analyze it.\n\n"
            "Example: `@kentik show me top talkers in the last hour`"
        )
        await post_message(client, channel_id, help_text, thread_ts or event_ts)
        return

    # Get bot user ID
    try:
        auth_response = await client.auth_test()
        bot_user_id = auth_response["user_id"]
    except SlackApiError as e:
        logger.error(f"failed to get bot user ID: {e.response['error']}")
        return

    # If not in a thread, use event timestamp as the thread parent
    if not thread_ts:
        thread_ts = event_ts

    await ctx.engine.handle_question(
        client, channel_id, thread_ts, question, bot_user_id, event_ts
    )
