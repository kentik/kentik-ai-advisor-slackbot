import logging
from typing import Any

from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus
from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx

logger = logging.getLogger(__file__)


@ctx.assistant.thread_started
async def handle_assistant_thread_started(
    say: AsyncSay,
):
    """Handle assistant thread started event."""
    logger.info("assistant thread started")
    await say(
        ":wave: Hi! I'm Kentik AI Advisor. I can help you analyze your network data. Ask me anything about your network!"
    )


@ctx.assistant.user_message
async def handle_assistant_user_message(
    payload: dict[str, Any],
    say: AsyncSay,
    client: AsyncWebClient,
    set_status: AsyncSetStatus,
):
    """Handle user messages in assistant thread."""
    logger.info("assistant user message received")
    logger.debug(f"payload: {payload}")

    channel_id = payload.get("channel")
    thread_ts = payload.get("thread_ts")
    question = payload.get("text", "").strip()

    if not question:
        await say("Please ask a question about your network.")
        return

    await set_status("Thinking...")

    await ctx.engine.handle_question(
        client=client,
        channel_id=channel_id,
        thread_ts=thread_ts,
        question=question,
        event_ts=payload.get("ts"),
    )
