from __future__ import annotations

from typing import Optional

import aiosqlite

from .models import get_db


class UserRepo:
    @staticmethod
    async def get_by_tg_id(tg_id: int) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_school_login(login: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE school_login = ? AND status = 'approved'",
                (login,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_school_login_any_status(login: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE school_login = ?",
                (login,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def find_by_identifier(identifier: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            try:
                tg_id = int(identifier)
                async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cur:
                    row = await cur.fetchone()
                    if row:
                        return row
            except ValueError:
                pass

            async with db.execute(
                "SELECT * FROM users WHERE school_login = ?",
                (identifier.lower(),),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    return row

            async with db.execute(
                "SELECT * FROM users WHERE tg_name LIKE ? OR tg_name LIKE ? LIMIT 1",
                (f"%{identifier}%", f"%@{identifier}%"),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_by_invite_link(invite_link: str) -> Optional[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE invite_link = ?",
                (invite_link,),
            ) as cur:
                return await cur.fetchone()

    @staticmethod
    async def get_approved_users() -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE status = 'approved' AND school_login IS NOT NULL AND (is_guest = 0 OR is_guest IS NULL)"
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def get_approved_users_all() -> list[aiosqlite.Row]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE status = 'approved' AND school_login IS NOT NULL"
            ) as cur:
                return await cur.fetchall()

    @staticmethod
    async def upsert_basic(tg_id: int, tg_name: str) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (tg_id, tg_name) VALUES (?, ?) "
                "ON CONFLICT(tg_id) DO UPDATE SET tg_name = excluded.tg_name",
                (tg_id, tg_name),
            )
            await db.commit()

    @staticmethod
    async def approve(
        tg_id,
        moderator_id,
        moderator_name,
        school_login,
        coalition,
        invite_link,
        decision_date,
    ) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET status='approved', school_login=?, coalition=?, "
                "invite_link=?, invite_user_id=?, moderator_id=?, moderator_name=?, decision_date=? "
                "WHERE tg_id=?",
                (school_login, coalition, invite_link, tg_id, moderator_id, moderator_name, decision_date, tg_id),
            )
            await db.commit()

    @staticmethod
    async def reject(tg_id: int, moderator_id: int, moderator_name: str, decision_date: str) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET status='rejected', moderator_id=?, moderator_name=?, decision_date=? WHERE tg_id=?",
                (moderator_id, moderator_name, decision_date, tg_id),
            )
            await db.commit()

    @staticmethod
    async def set_application_date(tg_id: int, date: str) -> None:
        async with get_db() as db:
            await db.execute("UPDATE users SET application_date=? WHERE tg_id=?", (date, tg_id))
            await db.commit()

    @staticmethod
    async def set_cooldown(tg_id: int, seconds: int) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET cooldown_until = datetime('now', ? || ' seconds') WHERE tg_id=?",
                (str(seconds), tg_id),
            )
            await db.commit()

    @staticmethod
    async def get_cooldown_message(tg_id: int) -> Optional[str]:
        async with get_db() as db:
            async with db.execute(
                "SELECT CAST((julianday(cooldown_until) - julianday('now')) * 86400 AS INTEGER) as secs_left "
                "FROM users WHERE tg_id=? AND cooldown_until > datetime('now')",
                (tg_id,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        secs = row["secs_left"]
        if secs <= 0:
            return None
        if secs < 3600:
            human = f"{secs // 60} мин."
        elif secs < 86400:
            human = f"{secs // 3600} ч."
        else:
            human = f"{secs // 86400} д."
        return f"⏳ Повторная подача заявки будет доступна через <b>{human}</b>.\nПопробуйте позже."

    @staticmethod
    async def set_banned(tg_id: int, banned: bool) -> None:
        async with get_db() as db:
            await db.execute("UPDATE users SET is_banned=? WHERE tg_id=?", (1 if banned else 0, tg_id))
            await db.commit()

    @staticmethod
    async def change_login(tg_id: int, new_login: str, new_coalition: str | None) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET school_login=?, coalition=? WHERE tg_id=?",
                (new_login, new_coalition, tg_id),
            )
            await db.commit()

    @staticmethod
    async def set_rocket_username(tg_id: int, rc_username: str) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET rocket_username=? WHERE tg_id=?",
                (rc_username, tg_id),
            )
            await db.commit()

    @staticmethod
    async def delete_user(tg_id: int) -> None:
        async with get_db() as db:
            await db.execute("DELETE FROM applications WHERE tg_id = ?", (tg_id,))
            await db.execute("DELETE FROM users WHERE tg_id = ?", (tg_id,))
            await db.commit()

    @staticmethod
    async def clear_all() -> None:
        async with get_db() as db:
            await db.execute("DELETE FROM applications")
            await db.execute("DELETE FROM users")
            await db.commit()
