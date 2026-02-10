from dataclasses import dataclass

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.middleware.assistant.async_assistant import AsyncAssistant

from kentik_ai_advisor_slackbot.ai_advisor_client import AIAdvisorClient
from kentik_ai_advisor_slackbot.conversation_store import ConversationStore


@dataclass
class SlackContext:
    app: AsyncApp
    assistant: AsyncAssistant
    advisor: AIAdvisorClient
    store: ConversationStore
