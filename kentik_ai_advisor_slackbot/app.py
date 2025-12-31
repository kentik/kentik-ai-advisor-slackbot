"""Main Kentik AI Advisor Slackbot application."""

import os
import re
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .ai_advisor_client import AIAdvisorClient
from .conversation_store import ConversationStore

load_dotenv()

# Environment variables
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN").strip('\'"')
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN").strip('\'"')
KENTIK_API_URL = os.getenv("KENTIK_API_URL").strip('\'"')
KENTIK_API_EMAIL = os.getenv("KENTIK_API_EMAIL").strip('\'"')
KENTIK_API_TOKEN = os.getenv("KENTIK_API_TOKEN").strip('\'"')
THREAD_CONTEXT_MESSAGES = int(os.getenv("THREAD_CONTEXT_MESSAGES", "20").strip('\'"'))
POLLING_TIMEOUT_SECONDS = int(os.getenv("POLLING_TIMEOUT_SECONDS", "120").strip('\'"'))
POLLING_INTERVAL_SECONDS = int(os.getenv("POLLING_INTERVAL_SECONDS", "2").strip('\'"'))
CONVERSATIONS_DB_PATH = os.getenv("CONVERSATIONS_DB_PATH", "conversations.db").strip('\'"')

# Validate required environment variables
if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, KENTIK_API_URL, KENTIK_API_EMAIL, KENTIK_API_TOKEN]):
    raise EnvironmentError(
        "Required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, "
        "KENTIK_API_URL, KENTIK_API_EMAIL, KENTIK_API_TOKEN"
    )

# Initialize components
app = App(token=SLACK_BOT_TOKEN)
ai_advisor = AIAdvisorClient(
    api_url=KENTIK_API_URL,
    api_email=KENTIK_API_EMAIL,
    api_token=KENTIK_API_TOKEN,
    poll_interval=POLLING_INTERVAL_SECONDS,
    timeout=POLLING_TIMEOUT_SECONDS,
)
conversation_store = ConversationStore(db_path=CONVERSATIONS_DB_PATH)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_thread_messages(
    client: WebClient, channel_id: str, thread_ts: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """Retrieve messages from a Slack thread.

    Args:
        client: Slack WebClient
        channel_id: Channel ID
        thread_ts: Thread timestamp
        limit: Maximum number of messages to retrieve

    Returns:
        List of message dictionaries
    """
    try:
        response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=limit,
        )
        return response.get("messages", [])
    except SlackApiError as e:
        logger.error(f"Failed to get thread messages: {e.response['error']}")
        return []


def extract_user_messages(
    messages: List[Dict[str, Any]], bot_user_id: str, from_index: int = 0
) -> List[str]:
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

        # Skip bot messages and empty messages
        if user_id == bot_user_id or not text:
            continue

        # Remove bot mentions from text
        text = re.sub(r"<@\w+>", "", text).strip()
        if text:
            user_messages.append(text)

    return user_messages


def get_messages_since_last_bot_reply(
    messages: List[Dict[str, Any]], bot_user_id: str, current_msg_ts: str
) -> List[str]:
    """Get all user messages since the last bot reply.

    Args:
        messages: List of Slack messages in thread
        bot_user_id: Bot's user ID
        current_msg_ts: Timestamp of current message (to exclude)

    Returns:
        List of user message texts since last bot message
    """
    # Find the last bot message before the current message
    last_bot_index = -1
    current_msg_index = -1

    for i, msg in enumerate(messages):
        if msg.get("ts") == current_msg_ts:
            current_msg_index = i
            break
        if msg.get("user") == bot_user_id:
            last_bot_index = i

    # If we found a bot message, get all user messages after it
    if last_bot_index >= 0 and current_msg_index > last_bot_index:
        user_messages = extract_user_messages(
            messages[last_bot_index + 1:current_msg_index], bot_user_id
        )
        return user_messages

    return []


def get_portal_url() -> str:
    """Get Kentik portal URL based on API URL.

    Returns:
        Portal URL (US or EU cluster)
    """
    api_url = KENTIK_API_URL.lower()
    if "kentik.eu" in api_url or ".eu" in api_url:
        return "https://portal.kentik.eu"
    else:
        return "https://portal.kentik.com"


def format_markdown_for_slack(markdown: str) -> str:
    """Convert AI Advisor markdown to Slack mrkdwn format.

    Args:
        markdown: Markdown text from AI Advisor

    Returns:
        Slack-formatted text
    """
    text = markdown

    # Convert double-star bold to single-star bold (**text** → *text*)
    # Slack uses single stars for bold, markdown uses double stars
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    # Convert headers to bold
    text = re.sub(r"^#### (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*?)$", r"*\1*", text, flags=re.MULTILINE)

    # Convert tables BEFORE converting links (links contain | which confuses table detection)
    # Detect table and convert to code block
    lines = text.split("\n")
    formatted_lines = []
    in_table = False
    table_lines = []

    for i, line in enumerate(lines):
        # Detect table start (line with | and likely a header)
        # Check if next line is also a table line to confirm
        is_table_line = "|" in line and line.strip()

        if is_table_line and not in_table:
            # Start collecting table lines
            in_table = True
            table_lines = [line]
        elif in_table:
            if "|" in line and line.strip():
                # Continue collecting table lines
                table_lines.append(line)
            else:
                # End of table, output as code block
                if table_lines:
                    formatted_lines.append("```")
                    formatted_lines.extend(table_lines)
                    formatted_lines.append("```")
                    table_lines = []
                in_table = False
                # Add the non-table line
                if line.strip():  # Only add if not empty
                    formatted_lines.append(line)
                elif formatted_lines:  # Preserve empty lines between sections
                    formatted_lines.append(line)
        else:
            # Regular line, not in table
            formatted_lines.append(line)

    # Handle table at end of text
    if table_lines:
        formatted_lines.append("```")
        formatted_lines.extend(table_lines)
        formatted_lines.append("```")

    text = "\n".join(formatted_lines)

    # NOW convert markdown links to Slack format (after tables are processed)
    # Get portal URL for link conversion
    portal_url = get_portal_url()

    # Convert markdown links to Slack format
    # [text](/v4/path) → <https://portal.kentik.com/v4/path|text>
    def replace_link(match):
        link_text = match.group(1)
        link_path = match.group(2)
        # Add portal URL if path starts with /v4/
        if link_path.startswith("/v4/"):
            full_url = f"{portal_url}{link_path}"
            return f"<{full_url}|{link_text}>"
        # For other paths, use as-is
        elif link_path.startswith("http"):
            return f"<{link_path}|{link_text}>"
        else:
            # Relative path, add portal URL
            full_url = f"{portal_url}{link_path}"
            return f"<{full_url}|{link_text}>"

    # Convert [text](url) format
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, text)

    return text


def post_message(
    client: WebClient, channel: str, text: str, thread_ts: Optional[str] = None
) -> Optional[str]:
    """Post a message to Slack.

    Args:
        client: Slack WebClient
        channel: Channel ID
        text: Message text
        thread_ts: Optional thread timestamp to reply in thread

    Returns:
        Message timestamp or None on error
    """
    try:
        response = client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
            unfurl_links=False,
        )
        return response["ts"]
    except SlackApiError as e:
        logger.error(f"Failed to post message: {e.response['error']}")
        return None


def update_message(
    client: WebClient, channel: str, ts: str, text: str
) -> None:
    """Update an existing Slack message.

    Args:
        client: Slack WebClient
        channel: Channel ID
        ts: Message timestamp
        text: New message text
    """
    try:
        client.chat_update(channel=channel, ts=ts, text=text, unfurl_links=False)
    except SlackApiError as e:
        logger.error(f"Failed to update message: {e.response['error']}")


def process_ai_advisor_response(
    client: WebClient,
    channel_id: str,
    thread_ts: str,
    response: Dict[str, Any],
    status_ts: str,
) -> None:
    """Process and post AI Advisor response to Slack.

    This replaces any intermediate reasoning with the final answer.

    Args:
        client: Slack WebClient
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
                update_message(client, channel_id, status_ts, slack_text)
            elif error_message:
                update_message(
                    client,
                    channel_id,
                    status_ts,
                    f"AI Advisor encountered an error: {error_message}",
                )
            else:
                update_message(
                    client,
                    channel_id,
                    status_ts,
                    "AI Advisor completed but returned no answer.",
                )
        else:
            update_message(
                client, channel_id, status_ts, "AI Advisor completed but returned no messages."
            )

    elif status == "SESSION_STATUS_FAILED":
        messages = response.get("messages", [])
        error_msg = "AI Advisor request failed."
        if messages:
            error_message = messages[-1].get("errorMessage", "")
            if error_message:
                error_msg = f"AI Advisor failed: {error_message}"

        update_message(client, channel_id, status_ts, error_msg)

    else:
        update_message(
            client, channel_id, status_ts, "AI Advisor request timed out. Please try again."
        )


def poll_with_reasoning_updates(
    client: WebClient,
    channel_id: str,
    status_ts: str,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """Poll AI Advisor with live reasoning updates.

    Args:
        client: Slack WebClient
        channel_id: Channel ID
        status_ts: Message timestamp to update
        session_id: AI Advisor session ID

    Returns:
        Completed session data or None on timeout
    """
    import time

    elapsed = 0
    last_reasoning = ""
    update_interval = POLLING_INTERVAL_SECONDS

    logger.info(f"Polling for completion of session {session_id} with reasoning updates...")

    while elapsed < POLLING_TIMEOUT_SECONDS:
        try:
            response = ai_advisor.get_chat_session(session_id)
            status = response.get("status")
            messages = response.get("messages", [])

            logger.debug(f"Session {session_id} status: {status}")

            # Check for reasoning updates
            if messages:
                latest_message = messages[-1]
                current_reasoning = latest_message.get("reasoning", "").strip()

                # Update message if reasoning has changed
                if current_reasoning and current_reasoning != last_reasoning:
                    last_reasoning = current_reasoning
                    reasoning_text = f"_Thinking..._\n\n{current_reasoning}"
                    update_message(client, channel_id, status_ts, reasoning_text)
                    logger.debug(f"Updated reasoning: {current_reasoning[:100]}...")

            # Check if completed
            if status == "SESSION_STATUS_COMPLETED":
                logger.info(f"Session {session_id} completed successfully")
                return response
            elif status == "SESSION_STATUS_FAILED":
                logger.error(f"Session {session_id} failed")
                return response

        except Exception as e:
            logger.error(f"Error polling session: {e}")

        time.sleep(update_interval)
        elapsed += update_interval

    logger.warning(f"Session {session_id} timed out after {POLLING_TIMEOUT_SECONDS}s")
    return None


def handle_ai_advisor_question(
    client: WebClient,
    channel_id: str,
    thread_ts: Optional[str],
    question: str,
    bot_user_id: str,
    event_ts: Optional[str] = None,
) -> None:
    """Handle AI Advisor question from Slack.

    Args:
        client: Slack WebClient
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
        session_id = conversation_store.get_session_id(thread_ts)

        if session_id:
            # This is a follow-up in an existing conversation
            logger.info(f"Follow-up question in thread {thread_ts}, session {session_id}")

            # Get recent user messages since last bot reply for context
            if event_ts:
                messages = get_thread_messages(client, channel_id, thread_ts)
                recent_context = get_messages_since_last_bot_reply(
                    messages, bot_user_id, event_ts
                )

                # Include recent messages as context (exclude the current question)
                if recent_context:
                    logger.info(f"Including {len(recent_context)} recent message(s) as context")
                    context_text = "\n".join(f"- {msg}" for msg in recent_context)
                    prompt = (
                        f"Recent context from user (messages since my last reply):\n"
                        f"{context_text}\n\n"
                        f"Current question: {question}"
                    )
        else:
            # New conversation in a thread - get context from previous messages
            logger.info(f"New conversation in existing thread {thread_ts}")
            messages = get_thread_messages(client, channel_id, thread_ts)

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
        logger.info(f"New conversation in channel {channel_id}")

    # Add Slack markdown instruction to prompt
    prompt = f"{prompt}\n\nYou must use only Slack markdown and NO tables in the outputs of this session."

    # Post initial status message
    if thread_ts:
        status_ts = post_message(
            client, channel_id, "Processing your question...", thread_ts
        )
    else:
        # This will create a thread
        status_ts = post_message(
            client, channel_id, "Processing your question..."
        )
        # The status message becomes the thread parent
        thread_ts = status_ts

    if not status_ts:
        logger.error("Failed to post status message")
        return

    # Query AI Advisor
    logger.info(f"Asking AI Advisor: {prompt[:100]}...")

    try:
        # Create or update session
        if session_id:
            response = ai_advisor.update_chat_session(session_id, prompt)
            new_session_id = session_id
        else:
            response = ai_advisor.create_chat_session(prompt)
            new_session_id = response.get("id")

        if not new_session_id:
            logger.error("No session ID returned from AI Advisor")
            update_message(
                client,
                channel_id,
                status_ts,
                "Failed to create AI Advisor session. Please try again later.",
            )
            return

        # Save conversation mapping
        if thread_ts:
            conversation_store.save_conversation(thread_ts, channel_id, new_session_id)

        # Poll with reasoning updates
        final_response = poll_with_reasoning_updates(
            client, channel_id, status_ts, new_session_id
        )

        if final_response:
            # Process and post final response
            process_ai_advisor_response(
                client, channel_id, thread_ts, final_response, status_ts
            )
        else:
            update_message(
                client,
                channel_id,
                status_ts,
                "AI Advisor request timed out. Please try again later.",
            )

    except Exception as e:
        logger.error(f"Error querying AI Advisor: {e}")
        update_message(
            client,
            channel_id,
            status_ts,
            "Failed to get response from AI Advisor. Please try again later.",
        )


@app.event("app_mention")
def handle_app_mention(event: Dict[str, Any], client: WebClient):
    """Handle @mentions of the bot.

    Args:
        event: Slack event data
        client: Slack WebClient
    """
    logger.info(f"Received app_mention event: {event.get('type')}")
    logger.debug(f"Full event: {event}")

    text = event.get("text", "").strip()
    user_id = event.get("user")
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts")  # None if in main channel
    event_ts = event.get("ts")

    logger.info(f"Processing mention from user {user_id} in channel {channel_id}")

    # Remove bot mention from text
    question = re.sub(r"<@\w+>", "", text).strip()

    if not question:
        help_text = (
            "Hello! I'm the Kentik AI Advisor bot. "
            "Mention me with a question about your network and I'll help you analyze it.\n\n"
            "Example: `@kentik show me top talkers in the last hour`"
        )
        post_message(client, channel_id, help_text, thread_ts or event_ts)
        return

    # Get bot user ID
    try:
        auth_response = client.auth_test()
        bot_user_id = auth_response["user_id"]
    except SlackApiError as e:
        logger.error(f"Failed to get bot user ID: {e.response['error']}")
        return

    # If not in a thread, use event timestamp as the thread parent
    if not thread_ts:
        thread_ts = event_ts

    # Handle the question
    handle_ai_advisor_question(client, channel_id, thread_ts, question, bot_user_id, event_ts)


@app.event("message")
def handle_message(event: Dict[str, Any], client: WebClient):
    """Handle direct messages to the bot.

    Args:
        event: Slack event data
        client: Slack WebClient
    """
    logger.info(f"Received message event: {event.get('type')}")
    logger.debug(f"Full event: {event}")

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

    logger.info(f"Processing message from user {user_id} in channel {channel_id}")

    # Get bot user ID
    try:
        auth_response = client.auth_test()
        bot_user_id = auth_response["user_id"]
    except SlackApiError as e:
        logger.error(f"Failed to get bot user ID: {e.response['error']}")
        return

    # Handle as new conversation (no threading in DMs)
    handle_ai_advisor_question(client, channel_id, None, question, bot_user_id, event.get("ts"))


def main():
    """Start the Slackbot application."""
    logger.info("Starting AI Advisor Slackbot...")
    logger.info(f"Bot token: {SLACK_BOT_TOKEN[:15]}... (length: {len(SLACK_BOT_TOKEN)})")
    logger.info(f"App token: {SLACK_APP_TOKEN[:15]}... (length: {len(SLACK_APP_TOKEN)})")
    logger.info(f"Kentik API URL: {KENTIK_API_URL}")
    logger.info("Connecting to Slack via Socket Mode...")

    try:
        handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        logger.info("✓ Socket Mode handler created successfully")
        logger.info("✓ Bot is now listening for events...")
        logger.info("  - Listening for @mentions in channels")
        logger.info("  - Listening for direct messages")
        handler.start()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    main()
