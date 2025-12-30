"""SQLite-based storage for Slack thread to AI Advisor conversation mapping."""

import sqlite3
import logging
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConversationStore:
    """Manages mapping between Slack threads and AI Advisor conversation IDs."""

    def __init__(self, db_path: str = "conversations.db"):
        """Initialize the conversation store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    thread_ts TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def save_conversation(
        self, thread_ts: str, channel_id: str, session_id: str
    ) -> None:
        """Save or update a conversation mapping.

        Args:
            thread_ts: Slack thread timestamp
            channel_id: Slack channel ID
            session_id: AI Advisor session UUID
        """
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (thread_ts, channel_id, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_ts) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (thread_ts, channel_id, session_id, now, now),
            )
            conn.commit()
            logger.info(f"Saved conversation: thread={thread_ts}, session={session_id}")

    def get_session_id(self, thread_ts: str) -> Optional[str]:
        """Get AI Advisor session ID for a Slack thread.

        Args:
            thread_ts: Slack thread timestamp

        Returns:
            AI Advisor session UUID or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id FROM conversations WHERE thread_ts = ?",
                (thread_ts,),
            )
            row = cursor.fetchone()

            if row:
                session_id = row["session_id"]
                logger.debug(f"Found session {session_id} for thread {thread_ts}")
                return session_id

            logger.debug(f"No session found for thread {thread_ts}")
            return None

    def delete_conversation(self, thread_ts: str) -> None:
        """Delete a conversation mapping.

        Args:
            thread_ts: Slack thread timestamp
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE thread_ts = ?", (thread_ts,))
            conn.commit()
            logger.info(f"Deleted conversation for thread {thread_ts}")

    def get_all_conversations(self):
        """Get all conversation mappings.

        Returns:
            List of conversation records
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]
