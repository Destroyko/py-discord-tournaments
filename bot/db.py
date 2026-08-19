import datetime
from dataclasses import dataclass
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    tournament_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    current_cycle_id INTEGER
);

CREATE TABLE IF NOT EXISTS registration_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_name TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    opened_by TEXT NOT NULL,
    closed_by TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES registration_cycles(id),
    discord_user_id TEXT NOT NULL,
    discord_username TEXT NOT NULL,
    faceit_link TEXT NOT NULL,
    steam_link TEXT NOT NULL DEFAULT '',
    comment TEXT,
    submitted_at TEXT NOT NULL,
    UNIQUE (cycle_id, discord_user_id)
);
"""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class TournamentState:
    tournament_name: Optional[str]
    is_active: bool
    current_cycle_id: Optional[int]


class Database:
    """Тонкий слой доступа к SQLite. Одно соединение на процесс бота."""

    def __init__(self, path: str):
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.execute(
            "INSERT OR IGNORE INTO state (id, tournament_name, is_active, current_cycle_id) "
            "VALUES (1, NULL, 0, NULL)"
        )
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Добивает схему для БД, созданных до появления новых колонок."""
        assert self._conn is not None
        async with self._conn.execute("PRAGMA table_info(applications)") as cursor:
            columns = {row[1] async for row in cursor}
        if "steam_link" not in columns:
            await self._conn.execute(
                "ALTER TABLE applications ADD COLUMN steam_link TEXT NOT NULL DEFAULT ''"
            )

        async with self._conn.execute("PRAGMA table_info(registration_cycles)") as cursor:
            cycle_columns = {row[1] async for row in cursor}
        if "closed_by" not in cycle_columns:
            await self._conn.execute(
                "ALTER TABLE registration_cycles ADD COLUMN closed_by TEXT"
            )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def get_state(self) -> TournamentState:
        assert self._conn is not None
        async with self._conn.execute(
            "SELECT tournament_name, is_active, current_cycle_id FROM state WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
        return TournamentState(tournament_name=row[0], is_active=bool(row[1]), current_cycle_id=row[2])

    async def open_cycle(self, tournament_name: str, opened_by: str) -> int:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "INSERT INTO registration_cycles (tournament_name, opened_at, opened_by) VALUES (?, ?, ?)",
            (tournament_name, _now(), opened_by),
        )
        cycle_id = cursor.lastrowid
        await self._conn.execute(
            "UPDATE state SET tournament_name = ?, is_active = 1, current_cycle_id = ? WHERE id = 1",
            (tournament_name, cycle_id),
        )
        await self._conn.commit()
        return cycle_id

    async def close_cycle(self, closed_by: str) -> None:
        assert self._conn is not None
        state = await self.get_state()
        if state.current_cycle_id is not None:
            await self._conn.execute(
                "UPDATE registration_cycles SET closed_at = ?, closed_by = ? WHERE id = ? AND closed_at IS NULL",
                (_now(), closed_by, state.current_cycle_id),
            )
        await self._conn.execute("UPDATE state SET is_active = 0 WHERE id = 1")
        await self._conn.commit()

    async def has_applied(self, cycle_id: int, discord_user_id: int) -> bool:
        assert self._conn is not None
        async with self._conn.execute(
            "SELECT 1 FROM applications WHERE cycle_id = ? AND discord_user_id = ?",
            (cycle_id, str(discord_user_id)),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def insert_application(
        self,
        cycle_id: int,
        discord_user_id: int,
        discord_username: str,
        faceit_link: str,
        steam_link: str,
        comment: Optional[str],
    ) -> bool:
        """Возвращает False, если заявка уже существует (гонка на уникальном ограничении)."""
        assert self._conn is not None
        try:
            await self._conn.execute(
                """
                INSERT INTO applications
                    (cycle_id, discord_user_id, discord_username, faceit_link, steam_link, comment, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cycle_id, str(discord_user_id), discord_username, faceit_link, steam_link, comment, _now()),
            )
            await self._conn.commit()
            return True
        except aiosqlite.IntegrityError:
            await self._conn.rollback()
            return False
