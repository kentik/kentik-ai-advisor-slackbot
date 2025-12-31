"""Kentik AI Advisor REST API client."""

import os
import time
import logging
from typing import Dict, Any, Optional

import requests

from . import __version__

logger = logging.getLogger(__name__)


class AIAdvisorClient:
    """Client for interacting with Kentik AI Advisor REST API."""

    def __init__(
        self,
        api_url: str,
        api_email: str,
        api_token: str,
        poll_interval: int = 2,
        timeout: int = 120,
    ):
        """Initialize the AI Advisor client.

        Args:
            api_url: Kentik API URL (e.g., https://grpc.api.kentik.com)
            api_email: Kentik account email
            api_token: Kentik API token
            poll_interval: Polling interval in seconds (default: 2, minimum: 2)
            timeout: Maximum wait time for response in seconds (default: 120)
        """
        self.api_url = api_url.rstrip("/")
        self.base_path = "/ai_advisor/v202511"
        self.poll_interval = max(2, poll_interval)  # Minimum 2 seconds
        self.timeout = timeout

        self.headers = {
            "X-CH-Auth-Email": api_email,
            "X-CH-Auth-API-Token": api_token,
            "User-Agent": f"kentik-ai-advisor-slackbot/{__version__}",
            "Content-Type": "application/json",
        }

    def create_chat_session(self, prompt: str) -> Dict[str, Any]:
        """Create a new chat session with initial prompt.

        Args:
            prompt: Initial question/prompt for AI Advisor

        Returns:
            Response containing session id and status

        Raises:
            requests.RequestException: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat"
        payload = {"prompt": prompt}

        logger.info(f"Creating chat session with prompt: {prompt[:100]}...")
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Chat session created: {result.get('id')}")
        return result

    def get_chat_session(self, session_id: str) -> Dict[str, Any]:
        """Get chat session status and results.

        Args:
            session_id: UUID of the chat session

        Returns:
            Response containing session status and messages

        Raises:
            requests.RequestException: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat/{session_id}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        return response.json()

    def update_chat_session(self, session_id: str, prompt: str) -> Dict[str, Any]:
        """Add follow-up question to existing conversation.

        Args:
            session_id: UUID of the existing chat session
            prompt: Follow-up question

        Returns:
            Response containing session id and status

        Raises:
            requests.RequestException: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat"
        payload = {"id": session_id, "prompt": prompt}

        logger.info(f"Updating chat session {session_id} with prompt: {prompt[:100]}...")
        response = requests.put(url, json=payload, headers=self.headers)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Chat session updated: {result.get('id')}")
        return result

    def wait_for_completion(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Poll for session completion.

        Args:
            session_id: UUID of the chat session

        Returns:
            Completed session data or None on timeout

        Raises:
            requests.RequestException: On API request failure
        """
        elapsed = 0
        logger.info(f"Polling for completion of session {session_id}...")

        while elapsed < self.timeout:
            response = self.get_chat_session(session_id)
            status = response.get("status")

            logger.debug(f"Session {session_id} status: {status}")

            if status == "SESSION_STATUS_COMPLETED":
                logger.info(f"Session {session_id} completed successfully")
                return response
            elif status == "SESSION_STATUS_FAILED":
                logger.error(f"Session {session_id} failed")
                return response

            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        logger.warning(f"Session {session_id} timed out after {self.timeout}s")
        return None

    def ask_question(self, prompt: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ask a question and wait for completion.

        Args:
            prompt: Question to ask
            session_id: Optional existing session ID for follow-up questions

        Returns:
            Completed session data or None on timeout/error
        """
        try:
            if session_id:
                response = self.update_chat_session(session_id, prompt)
            else:
                response = self.create_chat_session(prompt)

            session_id = response.get("id")
            if not session_id:
                logger.error("No session ID in response")
                return None

            return self.wait_for_completion(session_id)

        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
