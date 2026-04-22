from __future__ import annotations
import logging
import os
import aiosqlite

logger = logging.getLogger(__name__)
_DB_PATH: str = os.environ.get("DB_PATH", "data/bot.db")


class _ConnectionContextManager:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def __aenter__(self) -> aiosqlite.Connection:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._conn:
            await self._conn.close()


def get_db() -> _ConnectionContextManager:
    return _ConnectionContextManager(_DB_PATH)


async def init_db() -> None:
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id            INTEGER PRIMARY KEY,
                tg_name          TEXT,
                school_login     TEXT,
                coalition        TEXT,
                status           TEXT NOT NULL DEFAULT 'new',
                invite_link      TEXT,
                invite_user_id   INTEGER,
                moderator_id     INTEGER,
                moderator_name   TEXT,
                application_date TEXT,
                decision_date    TEXT,
                cooldown_until   TEXT,
                is_banned        INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id             INTEGER NOT NULL,
                tg_name           TEXT,
                school_login      TEXT,
                user_comment      TEXT,
                submitted_at      TEXT,
                status            TEXT NOT NULL DEFAULT 'pending',
                moderator_id      INTEGER,
                moderator_name    TEXT,
                decision_at       TEXT,
                reject_reason     TEXT,
                moderation_msg_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_attempts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id      INTEGER NOT NULL,
                tg_name    TEXT,
                login      TEXT,
                result     TEXT NOT NULL,
                reason     TEXT,
                attempted_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS otp_sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id        INTEGER NOT NULL,
                rc_username  TEXT    NOT NULL,
                code_hash    TEXT    NOT NULL,
                secret       TEXT    NOT NULL,
                attempts     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT    NOT NULL,
                expires_at   TEXT    NOT NULL,
                used         INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Safe migrations
        migrations = [
            ("users", "invite_user_id", "INTEGER"),
            ("users", "moderator_name", "TEXT"),
            ("applications", "moderator_name", "TEXT"),
            ("users", "rocket_username", "TEXT"),
            ("users", "is_guest", "INTEGER NOT NULL DEFAULT 0"),
            ("users", "home_campus", "TEXT"),
        ]
        for table, col, definition in migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                await db.commit()
                logger.info("Migration: added %s.%s", table, col)
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification_verifiers (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                verification_request_id   INTEGER NOT NULL,
                verifier_user_id          INTEGER NOT NULL,
                verifier_school_login     TEXT,
                source_teammate_auto      INTEGER NOT NULL DEFAULT 0,
                source_inline_selected    INTEGER NOT NULL DEFAULT 0,
                notification_sent_at      TEXT,
                vote                      TEXT,
                voted_at                  TEXT,
                is_active                 INTEGER NOT NULL DEFAULT 1,
                UNIQUE(verification_request_id, verifier_user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                code             TEXT    NOT NULL UNIQUE,
                creator_user_id  INTEGER NOT NULL,
                used_by_user_id  INTEGER,
                created_at       TEXT    NOT NULL,
                expires_at       TEXT,
                usage_limit      INTEGER NOT NULL DEFAULT 1,
                used_count       INTEGER NOT NULL DEFAULT 0,
                used_at          TEXT,
                trust_bonus      INTEGER NOT NULL DEFAULT 1,
                campus_id        TEXT,
                wave_id          TEXT,
                is_active        INTEGER NOT NULL DEFAULT 1
            )
        """)

        # invite_code_id FK on applications
        try:
            await db.execute(
                "ALTER TABLE applications ADD COLUMN invite_code_id INTEGER REFERENCES invite_codes(id)"
            )
            await db.commit()
            logger.info("Migration: added applications.invite_code_id")
        except Exception:
            pass


        await db.execute("""
            CREATE TABLE IF NOT EXISTS guest_invites (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id         INTEGER NOT NULL,
                school_login  TEXT    NOT NULL,
                home_campus   TEXT,
                invite_link   TEXT    NOT NULL,
                created_by    INTEGER NOT NULL,
                created_at    TEXT    NOT NULL,
                used          INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()
    logger.info("Database initialized at %s", _DB_PATH)
