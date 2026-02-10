import logging
from typing import Any

from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus

from kentik_ai_advisor_slackbot.ai_advisor_client import poll_ai_advisor_session
from kentik_ai_advisor_slackbot.app import ctx
from kentik_ai_advisor_slackbot.formatting import format_markdown_for_slack

logger = logging.getLogger(__file__)


@ctx.assistant.thread_started
async def handle_assistant_thread_started(
    say: AsyncSay,
):
    """Handle assistant thread started event."""
    logger.info("assistant thread started")
    await say(":wave: Hi! I'm Kentik AI Advisor. I can help you analyze your network data. Ask me anything about your network!")


@ctx.assistant.user_message
async def handle_assistant_user_message(
    payload: dict[str, Any],
    say: AsyncSay,
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

    # Check for existing session in this thread
    session_id = await ctx.store.get_session_id(thread_ts) if thread_ts else None

    # Build prompt
    prompt = f"{question}\n\nYou must use only Slack markdown and NO tables in the outputs of this session."

    try:
        # Create or update session
        if session_id:
            logger.info(f"continuing assistant session {session_id}")
            await ctx.advisor.update_chat_session(session_id, prompt)
            new_session_id = session_id
        else:
            logger.info("creating new assistant session")
            response = await ctx.advisor.create_chat_session(prompt)
            new_session_id = response.get("id")

        if not new_session_id:
            logger.error("no session ID returned from AI Advisor")
            await set_status("")
            await say("Failed to create AI Advisor session. Please try again later.")
            return

        # Save conversation mapping
        if thread_ts:
            await ctx.store.save_conversation(thread_ts, channel_id, new_session_id)

        # Poll with reasoning updates
        async def on_reasoning(reasoning: str) -> None:
            await set_status(f"Thinking: {reasoning[:100]}...")

        final_response = await poll_ai_advisor_session(ctx.advisor, new_session_id, on_reasoning)
        await set_status("")

        if not final_response:
            await say("AI Advisor request timed out. Please try again later.")
            return

        # Process response
        status = final_response.get("status")
        messages = final_response.get("messages", [])

        if status == "SESSION_STATUS_COMPLETED":
            if messages:
                latest_message = messages[-1]
                final_answer = latest_message.get("finalAnswer", "")
                error_message = latest_message.get("errorMessage", "")

                if final_answer:
                    await say(format_markdown_for_slack(final_answer))
                elif error_message:
                    await say(f"AI Advisor encountered an error: {error_message}")
                else:
                    await say("AI Advisor completed but returned no answer.")
            else:
                await say("AI Advisor completed but returned no messages.")

        elif status == "SESSION_STATUS_FAILED":
            error_msg = "AI Advisor request failed."
            if messages:
                error_message = messages[-1].get("errorMessage", "")
                if error_message:
                    error_msg = f"AI Advisor failed: {error_message}"
            await say(error_msg)

    except Exception as e:
        logger.error(f"error in assistant handler: {e}")
        await set_status("")
        await say("Failed to get response from AI Advisor. Please try again later.")
