import logging
from typing import Any

from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus
from slack_sdk.web.async_client import AsyncWebClient

from kentik_ai_advisor_slackbot.app import ctx
from kentik_ai_advisor_slackbot.slack_messages import resolve_mentions

logger = logging.getLogger(__file__)

SUGGESTED_PROMPTS = [
    {
        "title": "Show top talkers",
        "message": "Show me the top talkers on my network in the last hour",
    },
    {
        "title": "Investigate an anomaly",
        "message": "Are there any unusual traffic patterns I should know about?",
    },
]


@ctx.app.event("app_home_opened")
async def handle_app_home_opened(event: dict[str, Any], client: AsyncWebClient):
    """Show suggested prompts when a user opens a DM with the bot.

    Slack's Agent messaging experience (see
    https://docs.slack.dev/changelog/2026/06/30/agent-messages-tab) replaced
    `assistant_thread_started` with `app_home_opened` as the way to detect
    that a user has actively opened a DM/Messages tab conversation.
    """
    if event.get("tab") != "messages":
        return

    logger.info("messages tab opened, setting suggested prompts")

    try:
        await client.assistant_threads_setSuggestedPrompts(
            channel_id=event["channel"],
            title="Ask Kentik AI Advisor",
            prompts=SUGGESTED_PROMPTS,
        )
    except Exception as e:
        logger.error(f"failed to set suggested prompts: {e}")


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
    text = payload.get("text", "").strip()

    if not text:
        await say("Please ask a question about your network.")
        return

    await set_status("Thinking...")

    bot_user_id = await ctx.engine.get_bot_user_id(client)
    question = await resolve_mentions(client, text, bot_user_id)

    await ctx.engine.handle_question(
        client=client,
        channel_id=channel_id,
        thread_ts=thread_ts,
        question=question,
        event_ts=payload.get("ts"),
    )
