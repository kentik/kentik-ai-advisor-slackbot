"""Kentik AI Advisor REST API client."""

import asyncio
import logging
from typing import Any

import aiohttp

import importlib.metadata

try:
    __version__ = importlib.metadata.version("kentik-ai-advisor-mcp")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"


logger = logging.getLogger("kentik-ai-advisor-slackbot")


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
        self.poll_interval = max(2, poll_interval)
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

        self.headers = {
            "X-CH-Auth-Email": api_email,
            "X-CH-Auth-API-Token": api_token,
            "User-Agent": f"kentik-ai-advisor-slackbot/{__version__}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def create_chat_session(self, prompt: str) -> dict[str, Any]:
        """Create a new chat session with initial prompt.

        Args:
            prompt: Initial question/prompt for AI Advisor

        Returns:
            Response containing session id and status

        Raises:
            aiohttp.ClientError: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat"
        payload = {"prompt": prompt}

        logger.info(f"creating chat session with prompt: {prompt[:100]}...")
        session = await self._get_session()
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            result = await response.json()

        logger.info(f"chat session created: {result.get('id')}")
        return result

    async def get_chat_session(self, session_id: str) -> dict[str, Any]:
        """Get chat session status and results.

        Args:
            session_id: UUID of the chat session

        Returns:
            Response containing session status and messages

        Raises:
            aiohttp.ClientError: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat/{session_id}"

        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def update_chat_session(self, session_id: str, prompt: str) -> dict[str, Any]:
        """Add follow-up question to existing conversation.

        Args:
            session_id: UUID of the existing chat session
            prompt: Follow-up question

        Returns:
            Response containing session id and status

        Raises:
            aiohttp.ClientError: On API request failure
        """
        url = f"{self.api_url}{self.base_path}/chat"
        payload = {"id": session_id, "prompt": prompt}

        logger.info(f"updating chat session {session_id} with prompt: {prompt[:100]}...")
        session = await self._get_session()
        async with session.put(url, json=payload) as response:
            response.raise_for_status()
            result = await response.json()

        logger.info(f"chat session updated: {result.get('id')}")
        return result

    async def wait_for_completion(self, session_id: str) -> dict[str, Any] | None:
        """Poll for session completion.

        Args:
            session_id: UUID of the chat session

        Returns:
            Completed session data or None on timeout

        Raises:
            aiohttp.ClientError: On API request failure
        """
        elapsed = 0
        logger.info(f"polling for completion of session {session_id}...")

        while elapsed < self.timeout:
            response = await self.get_chat_session(session_id)
            status = response.get("status")

            logger.debug(f"session {session_id} status: {status}")

            if status == "SESSION_STATUS_COMPLETED":
                logger.info(f"session {session_id} completed successfully")
                return response
            elif status == "SESSION_STATUS_FAILED":
                logger.error(f"session {session_id} failed")
                return response

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        logger.warning(f"session {session_id} timed out after {self.timeout}s")
        return None

    async def ask_question(
        self, prompt: str, session_id: str | None = None
    ) -> dict[str, Any] | None:
        """Ask a question and wait for completion.

        Args:
            prompt: Question to ask
            session_id: Optional existing session ID for follow-up questions

        Returns:
            Completed session data or None on timeout/error
        """
        try:
            if session_id:
                response = await self.update_chat_session(session_id, prompt)
            else:
                response = await self.create_chat_session(prompt)

            session_id = response.get("id")
            if not session_id:
                logger.error("no session ID in response")
                return None

            return await self.wait_for_completion(session_id)

        except aiohttp.ClientError as e:
            logger.error(f"API request failed: {e}")
            return None
