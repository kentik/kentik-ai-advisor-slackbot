import logging
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx, handle_ai_advisor_question

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
    
    question = event.get("text", "").strip()
    channel_id = event.get("channel")
    user_id = event.get("user")
    
    if not question:
        return
    
    logger.info(f"processing message from user {user_id} in channel {channel_id}")
    
    # Get bot user ID
    try:
        auth_response = await client.auth_test()
        bot_user_id = auth_response["user_id"]
    except SlackApiError as e:
        logger.error(f"failed to get bot user ID: {e.response['error']}")
        return
    
    # Handle as new conversation (no threading in DMs)
    await handle_ai_advisor_question(client, channel_id, None, question, bot_user_id, event.get("ts"))
