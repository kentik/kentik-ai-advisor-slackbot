"""Slack thread and message operations."""

import re
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from .config import logger


async def get_thread_messages(
    client: AsyncWebClient, channel_id: str, thread_ts: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Retrieve messages from a Slack thread.

    Args:
        client: Slack AsyncWebClient
        channel_id: Channel ID
        thread_ts: Thread timestamp
        limit: Maximum number of messages to retrieve

    Returns:
        List of message dictionaries
    """
    try:
        response = await client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=limit,
        )
        return response.get("messages", [])
    except SlackApiError as e:
        logger.error(f"failed to get thread messages: {e.response['error']}")
        return []


def get_messages_since_last_bot_reply(
    messages: list[dict[str, Any]], bot_user_id: str, current_msg_ts: str
) -> list[str]:
    """Get all user messages since the last bot reply.

    Args:
        messages: List of Slack messages in thread
        bot_user_id: Bot's user ID
        current_msg_ts: Timestamp of current message (to exclude)

    Returns:
        List of user message texts since last bot message
    """
    last_bot_index = -1
    current_msg_index = -1

    for i, msg in enumerate(messages):
        if msg.get("ts") == current_msg_ts:
            current_msg_index = i
            break
        if msg.get("user") == bot_user_id:
            last_bot_index = i

    if last_bot_index >= 0 and current_msg_index > last_bot_index:
        user_messages = extract_user_messages(
            messages[last_bot_index + 1 : current_msg_index], bot_user_id
        )
        return user_messages

    return []


def extract_user_messages(
    messages: list[dict[str, Any]], bot_user_id: str, from_index: int = 0
) -> list[str]:
    """Extract user messages (excluding bot messages) from thread.

    Args:
        messages: List of Slack messages
        bot_user_id: Bot's user ID to filter out
        from_index: Start from this message index

    Returns:
        List of user message texts
    """
    user_messages = []
    for msg in messages[from_index:]:
        user_id = msg.get("user")
        text = msg.get("text", "").strip()

        if user_id == bot_user_id or not text:
            continue

        text = re.sub(r"<@\w+>", "", text).strip()
        if text:
            user_messages.append(text)

    return user_messages


async def post_message(
    client: AsyncWebClient, channel: str, text: str, thread_ts: str | None = None
) -> str | None:
    """Post a message to Slack.

    Args:
        client: Slack AsyncWebClient
        channel: Channel ID
        text: Message text
        thread_ts: Optional thread timestamp to reply in thread

    Returns:
        Message timestamp or None on error
    """
    try:
        response = await client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
            unfurl_links=False,
        )
        return response["ts"]
    except SlackApiError as e:
        logger.error(f"failed to post message: {e.response['error']}")
        return None


async def update_message(
    client: AsyncWebClient, channel: str, ts: str, text: str
) -> None:
    """Update an existing Slack message.

    Args:
        client: Slack AsyncWebClient
        channel: Channel ID
        ts: Message timestamp
        text: New message text
    """
    blocks = [
        {"type": "markdown", "text": text},
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": "This tool uses AI to generate responses, so some information may be inaccurate.",
                }
            ],
        }
    ]

    try:
        await client.chat_update(channel=channel, ts=ts, blocks=blocks, unfurl_links=False)
    except SlackApiError as e:
        logger.error(f"failed to update message: {e.response['error']}")
