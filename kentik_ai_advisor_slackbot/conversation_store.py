"""SQLite-based storage for Slack thread to AI Advisor conversation mapping."""

import logging
from datetime import datetime
from contextlib import asynccontextmanager

import aiosqlite

logger = logging.getLogger("kentik-ai-advisor-slackbot")


class ConversationStore:
    """Manages mapping between Slack threads and AI Advisor conversation IDs."""

    def __init__(self, db_path: str = "conversations.db"):
        """Initialize the conversation store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure the database is initialized."""
        if not self._initialized:
            await self._init_db()
            self._initialized = True

    async def _init_db(self) -> None:
        """Initialize the database schema."""
        async with self._get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    thread_ts TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await conn.commit()
            logger.info(f"database initialized at {self.db_path}")

    @asynccontextmanager
    async def _get_connection(self):
        """Get a database connection context manager."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def save_conversation(
        self, thread_ts: str, channel_id: str, session_id: str
    ) -> None:
        """Save or update a conversation mapping.

        Args:
            thread_ts: Slack thread timestamp
            channel_id: Slack channel ID
            session_id: AI Advisor session UUID
        """
        await self._ensure_initialized()
        now = datetime.utcnow().isoformat()

        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (thread_ts, channel_id, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_ts) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (thread_ts, channel_id, session_id, now, now),
            )
            await conn.commit()
            logger.info(f"saved conversation: thread={thread_ts}, session={session_id}")

    async def get_session_id(self, thread_ts: str) -> str | None:
        """Get AI Advisor session ID for a Slack thread.

        Args:
            thread_ts: Slack thread timestamp

        Returns:
            AI Advisor session UUID or None if not found
        """
        await self._ensure_initialized()

        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT session_id FROM conversations WHERE thread_ts = ?",
                (thread_ts,),
            )
            row = await cursor.fetchone()

            if row:
                session_id = row["session_id"]
                logger.debug(f"found session {session_id} for thread {thread_ts}")
                return session_id

            logger.debug(f"no session found for thread {thread_ts}")
            return None

    async def delete_conversation(self, thread_ts: str) -> None:
        """Delete a conversation mapping.

        Args:
            thread_ts: Slack thread timestamp
        """
        await self._ensure_initialized()

        async with self._get_connection() as conn:
            await conn.execute(
                "DELETE FROM conversations WHERE thread_ts = ?", (thread_ts,)
            )
            await conn.commit()
            logger.info(f"deleted conversation for thread {thread_ts}")

    async def get_all_conversations(self) -> list[dict]:
        """Get all conversation mappings.

        Returns:
            List of conversation records
        """
        await self._ensure_initialized()

        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
