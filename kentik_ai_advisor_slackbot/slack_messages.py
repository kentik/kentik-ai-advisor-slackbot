"""Slack thread and message operations."""

import re
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from .config import logger

MENTION_PATTERN = re.compile(r"<@(\w+)>")


async def resolve_mentions(
    client: AsyncWebClient, text: str, bot_user_id: str | None = None
) -> str:
    """Replace Slack user mentions with the mentioned user's email address.

    The bot's own mention is stripped, matching the previous behavior.
    Other mentioned users are replaced with their email so the AI Advisor
    prompt can reference the right person instead of an opaque Slack ID.

    Args:
        client: Slack AsyncWebClient
        text: Raw Slack message text, e.g. containing "<@U12345>"
        bot_user_id: Bot's user ID, stripped from the text rather than resolved

    Returns:
        Text with mentions replaced by email addresses (or stripped, for the bot)
    """
    user_ids = {match.group(1) for match in MENTION_PATTERN.finditer(text)}
    if not user_ids:
        return text.strip()

    replacements = {
        user_id: "" if user_id == bot_user_id else await _get_user_email(client, user_id)
        for user_id in user_ids
    }

    return MENTION_PATTERN.sub(lambda m: replacements[m.group(1)], text).strip()


async def _get_user_email(client: AsyncWebClient, user_id: str) -> str:
    """Look up a Slack user's email, falling back to their display name.

    Requires the users:read and users:read.email bot scopes.
    """
    try:
        response = await client.users_info(user=user_id)
        user = response.get("user", {})
        email = user.get("profile", {}).get("email")
        return email or user.get("real_name") or user.get("name") or user_id
    except SlackApiError as e:
        logger.error(f"failed to resolve user {user_id}: {e.response['error']}")
        return user_id


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


async def get_messages_since_last_bot_reply(
    client: AsyncWebClient,
    messages: list[dict[str, Any]],
    bot_user_id: str,
    current_msg_ts: str,
) -> list[str]:
    """Get all user messages since the last bot reply.

    Args:
        client: Slack AsyncWebClient
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
        return await extract_user_messages(
            client, messages[last_bot_index + 1 : current_msg_index], bot_user_id
        )

    return []


async def extract_user_messages(
    client: AsyncWebClient,
    messages: list[dict[str, Any]],
    bot_user_id: str,
    from_index: int = 0,
) -> list[str]:
    """Extract user messages (excluding bot messages) from thread.

    Args:
        client: Slack AsyncWebClient
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

        text = await resolve_mentions(client, text, bot_user_id)
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
