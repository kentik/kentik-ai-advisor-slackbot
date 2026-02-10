"""Main Kentik AI Advisor Slackbot application."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from slack_bolt.async_app import (
    AsyncApp,
    AsyncAssistant,
    AsyncSay,
    AsyncSetStatus,
    AsyncSetSuggestedPrompts,
    AsyncSetTitle,
)
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from kentik_ai_advisor_slackbot.context import SlackContext
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
    THREAD_CONTEXT_MESSAGES,
    logger,
)
from .conversation_store import ConversationStore
from .formatting import format_markdown_for_slack
from .slack_messages import (
    extract_user_messages,
    get_messages_since_last_bot_reply,
    get_thread_messages,
    post_message,
    update_message,
)

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
    store=conversation_store
)

app.use(assistant)


async def process_ai_advisor_response(
    client: AsyncWebClient,
    channel_id: str,
    thread_ts: str,
    response: dict[str, Any],
    status_ts: str,
) -> None:
    """Process and post AI Advisor response to Slack.

    This replaces any intermediate reasoning with the final answer.

    Args:
        client: Slack AsyncWebClient
        channel_id: Channel ID
        thread_ts: Thread timestamp
        response: AI Advisor response
        status_ts: Timestamp of status message to update
    """
    status = response.get("status")

    if status == "SESSION_STATUS_COMPLETED":
        messages = response.get("messages", [])
        if messages:
            latest_message = messages[-1]
            final_answer = latest_message.get("finalAnswer", "")
            error_message = latest_message.get("errorMessage", "")

            if final_answer:
                # Format and post the answer (replaces reasoning text)
                slack_text = format_markdown_for_slack(final_answer)
                await update_message(client, channel_id, status_ts, slack_text)
            elif error_message:
                await update_message(
                    client,
                    channel_id,
                    status_ts,
                    f"AI Advisor encountered an error: {error_message}",
                )
            else:
                await update_message(
                    client,
                    channel_id,
                    status_ts,
                    "AI Advisor completed but returned no answer.",
                )
        else:
            await update_message(
                client, channel_id, status_ts, "AI Advisor completed but returned no messages."
            )

    elif status == "SESSION_STATUS_FAILED":
        messages = response.get("messages", [])
        error_msg = "AI Advisor request failed."
        if messages:
            error_message = messages[-1].get("errorMessage", "")
            if error_message:
                error_msg = f"AI Advisor failed: {error_message}"

        await update_message(client, channel_id, status_ts, error_msg)

    else:
        await update_message(
            client, channel_id, status_ts, "AI Advisor request timed out. Please try again."
        )


async def poll_ai_advisor_session(
    session_id: str,
    on_reasoning: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any] | None:
    """Poll AI Advisor session until completion.

    Args:
        session_id: AI Advisor session ID
        on_reasoning: Optional async callback for reasoning updates

    Returns:
        Completed session data or None on timeout
    """
    elapsed = 0
    last_reasoning = ""

    logger.info(f"polling for completion of session {session_id}...")

    while elapsed < POLLING_TIMEOUT_SECONDS:
        try:
            response = await ai_advisor.get_chat_session(session_id)
            status = response.get("status")
            messages = response.get("messages", [])

            logger.debug(f"session {session_id} status: {status}")

            # Check for reasoning updates
            if on_reasoning and messages:
                latest_message = messages[-1]
                current_reasoning = latest_message.get("reasoning", "").strip()

                if current_reasoning and current_reasoning != last_reasoning:
                    last_reasoning = current_reasoning
                    await on_reasoning(current_reasoning)
                    logger.debug(f"updated reasoning: {current_reasoning[:100]}...")

            if status == "SESSION_STATUS_COMPLETED":
                logger.info(f"session {session_id} completed successfully")
                return response
            elif status == "SESSION_STATUS_FAILED":
                logger.error(f"session {session_id} failed")
                return response

        except Exception as e:
            logger.error(f"error polling session: {e}")

        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
        elapsed += POLLING_INTERVAL_SECONDS

    logger.warning(f"session {session_id} timed out after {POLLING_TIMEOUT_SECONDS}s")
    return None


async def handle_ai_advisor_question(
    client: AsyncWebClient,
    channel_id: str,
    thread_ts: str | None,
    question: str,
    bot_user_id: str,
    event_ts: str | None = None,
) -> None:
    """Handle AI Advisor question from Slack.

    Args:
        client: Slack AsyncWebClient
        channel_id: Channel ID
        thread_ts: Thread timestamp (None for main channel)
        question: User question
        bot_user_id: Bot's user ID
        event_ts: Timestamp of the triggering event (for context gathering)
    """
    # Determine if this is a new conversation or follow-up
    session_id = None
    prompt = question

    if thread_ts:
        # Check if this thread has an existing conversation
        session_id = await conversation_store.get_session_id(thread_ts)

        if session_id:
            # This is a follow-up in an existing conversation
            logger.info(f"follow-up question in thread {thread_ts}, session {session_id}")

            # Get recent user messages since last bot reply for context
            if event_ts:
                messages = await get_thread_messages(client, channel_id, thread_ts)
                recent_context = get_messages_since_last_bot_reply(
                    messages, bot_user_id, event_ts
                )

                # Include recent messages as context (exclude the current question)
                if recent_context:
                    logger.info(f"including {len(recent_context)} recent message(s) as context")
                    context_text = "\n".join(f"- {msg}" for msg in recent_context)
                    prompt = (
                        f"Recent context from user (messages since my last reply):\n"
                        f"{context_text}\n\n"
                        f"Current question: {question}"
                    )
        else:
            # New conversation in a thread - get context from previous messages
            logger.info(f"new conversation in existing thread {thread_ts}")
            messages = await get_thread_messages(client, channel_id, thread_ts)

            if len(messages) > 1:
                # Get the first message and previous N user messages
                first_msg = messages[0]
                first_text = first_msg.get("text", "").strip()
                first_text = re.sub(r"<@\w+>", "", first_text).strip()

                # Get context messages (excluding the current one)
                context_messages = extract_user_messages(
                    messages[1:-1], bot_user_id
                )[-THREAD_CONTEXT_MESSAGES:]

                # Build context prompt
                if context_messages:
                    context = "\n".join(f"- {msg}" for msg in context_messages)
                    prompt = (
                        f"Context from thread:\n"
                        f"Initial message: {first_text}\n"
                        f"Recent messages:\n{context}\n\n"
                        f"Current question: {question}"
                    )
                elif first_text:
                    prompt = f"Context: {first_text}\n\nQuestion: {question}"
    else:
        # New conversation in main channel - will reply in thread
        logger.info(f"new conversation in channel {channel_id}")

    # Add Slack markdown instruction to prompt
    prompt = f"{prompt}\n\nYou must use only Slack markdown and NO tables in the outputs of this session."

    # Post initial status message
    if thread_ts:
        status_ts = await post_message(
            client, channel_id, "Processing your question...", thread_ts
        )
    else:
        # This will create a thread
        status_ts = await post_message(
            client, channel_id, "Processing your question..."
        )
        # The status message becomes the thread parent
        thread_ts = status_ts

    if not status_ts:
        logger.error("failed to post status message")
        return

    # Query AI Advisor
    logger.info(f"asking AI Advisor: {prompt[:100]}...")

    try:
        # Create or update session
        if session_id:
            response = await ai_advisor.update_chat_session(session_id, prompt)
            new_session_id = session_id
        else:
            response = await ai_advisor.create_chat_session(prompt)
            new_session_id = response.get("id")

        if not new_session_id:
            logger.error("no session ID returned from AI Advisor")
            await update_message(
                client,
                channel_id,
                status_ts,
                "Failed to create AI Advisor session. Please try again later.",
            )
            return

        # Save conversation mapping
        if thread_ts:
            await conversation_store.save_conversation(thread_ts, channel_id, new_session_id)

        # Poll with reasoning updates
        async def on_reasoning(reasoning: str) -> None:
            await update_message(client, channel_id, status_ts, f"_Thinking..._\n\n{reasoning}")

        final_response = await poll_ai_advisor_session(new_session_id, on_reasoning)

        if final_response:
            # Process and post final response
            await process_ai_advisor_response(
                client, channel_id, thread_ts, final_response, status_ts
            )
        else:
            await update_message(
                client,
                channel_id,
                status_ts,
                "AI Advisor request timed out. Please try again later.",
            )

    except Exception as e:
        logger.error(f"error querying AI Advisor: {e}")
        await update_message(
            client,
            channel_id,
            status_ts,
            "Failed to get response from AI Advisor. Please try again later.",
        )


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
