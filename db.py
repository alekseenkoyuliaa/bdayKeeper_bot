"""Слой SQLite для бота дней рождений.

Две таблицы: user (кому слать) и person (чей день рождения).
Дату рождения храним как строку "MM-DD" — год не важен, повод повторяется
каждый год. last_notified хранит дату последней рассылки, чтобы не слать
одно и то же дважды в день (идемпотентность, как is_reminder_send в repo_b).
"""
import sqlite3
from datetime import date, datetime

from constants import LEAD_DAYS as DEFAULT_LEAD_DAYS
from constants import MSK
from constants import NOTIFY_HOUR as DEFAULT_NOTIFY_HOUR

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id           INTEGER PRIMARY KEY,      -- telegram user id
    name         TEXT,
    chat_id      INTEGER,                  -- куда слать напоминания
    remind_days  TEXT NOT NULL DEFAULT '', -- личное расписание: '' = дефолт, 'none' = только в день, иначе '7,3,1'
    notify_hour  TEXT NOT NULL DEFAULT ''  -- час рассылки (МСК): '' = глобальный дефолт, иначе '0'..'23'
);

CREATE TABLE IF NOT EXISTS person (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES user(id),
    name          TEXT    NOT NULL,       -- чей день рождения
    birthday      TEXT    NOT NULL,       -- "MM-DD"
    gift_idea     TEXT    NOT NULL DEFAULT '',
    last_notified TEXT    NOT NULL DEFAULT '',  -- ISO-дата последней рассылки
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_person_user ON person (user_id);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # миграции старых БД
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user)")}
    if "remind_days" not in cols:
        conn.execute("ALTER TABLE user ADD COLUMN remind_days TEXT NOT NULL DEFAULT ''")
    if "notify_hour" not in cols:
        conn.execute("ALTER TABLE user ADD COLUMN notify_hour TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def ensure_user(conn, user_id: int, name: str = "", chat_id: int | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO user (id, name, chat_id) VALUES (?, ?, ?)",
        (user_id, name, chat_id),
    )
    if chat_id is not None:
        conn.execute("UPDATE user SET name = ?, chat_id = ? WHERE id = ?",
                     (name, chat_id, user_id))
    conn.commit()


def get_chat_id(conn, user_id: int) -> int | None:
    row = conn.execute("SELECT chat_id FROM user WHERE id = ?", (user_id,)).fetchone()
    return row["chat_id"] if row else None


# --- личное расписание напоминаний ---

def get_remind_days(conn, user_id: int) -> list[int]:
    """За сколько дней напоминать этому пользователю.

    '' (не настраивал) -> глобальный дефолт из .env;
    'none'             -> только в сам день рождения (без «за N дней»);
    '7,3,1'            -> [7, 3, 1].
    """
    row = conn.execute("SELECT remind_days FROM user WHERE id = ?", (user_id,)).fetchone()
    raw = row["remind_days"] if row else ""
    if raw == "":
        return list(DEFAULT_LEAD_DAYS)
    if raw == "none":
        return []
    return [int(x) for x in raw.split(",") if x.isdigit()]


def set_remind_days(conn, user_id: int, raw: str) -> None:
    """Сохранить расписание: '' | 'none' | '7,3,1'."""
    conn.execute("UPDATE user SET remind_days = ? WHERE id = ?", (raw, user_id))
    conn.commit()


def get_notify_hour(conn, user_id: int) -> int:
    """В котором часу (МСК) слать этому пользователю. '' -> глобальный дефолт."""
    row = conn.execute("SELECT notify_hour FROM user WHERE id = ?", (user_id,)).fetchone()
    raw = row["notify_hour"] if row else ""
    return int(raw) if raw.isdigit() else DEFAULT_NOTIFY_HOUR


def set_notify_hour(conn, user_id: int, hour: int) -> None:
    conn.execute("UPDATE user SET notify_hour = ? WHERE id = ?", (str(hour), user_id))
    conn.commit()


# --- person CRUD (всё с фильтром по user_id: чужое недостижимо) ---

def add_person(conn, user_id: int, name: str, birthday: str, gift_idea: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO person (user_id, name, birthday, gift_idea, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, birthday, gift_idea, datetime.now(MSK).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def find_person(conn, user_id: int, name: str):
    return conn.execute(
        "SELECT * FROM person WHERE user_id = ? AND lower(name) = lower(?)",
        (user_id, name),
    ).fetchone()


def list_people(conn, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM person WHERE user_id = ? ORDER BY birthday", (user_id,)
    ).fetchall()


def set_gift_idea(conn, user_id: int, name: str, gift_idea: str) -> bool:
    cur = conn.execute(
        "UPDATE person SET gift_idea = ? WHERE user_id = ? AND lower(name) = lower(?)",
        (gift_idea, user_id, name),
    )
    conn.commit()
    return cur.rowcount > 0


def update_birthday(conn, user_id: int, name: str, birthday: str) -> bool:
    # last_notified сбрасываем: новая дата — новый повод напомнить в этом году
    cur = conn.execute(
        "UPDATE person SET birthday = ?, last_notified = '' "
        "WHERE user_id = ? AND lower(name) = lower(?)",
        (birthday, user_id, name),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_person(conn, user_id: int, name: str) -> bool:
    cur = conn.execute(
        "DELETE FROM person WHERE user_id = ? AND lower(name) = lower(?)",
        (user_id, name),
    )
    conn.commit()
    return cur.rowcount > 0


# --- для планировщика ---

def all_people(conn) -> list[sqlite3.Row]:
    """Все записи всех пользователей — планировщику, чтобы посчитать, у кого скоро ДР."""
    return conn.execute("SELECT * FROM person").fetchall()


def mark_notified(conn, person_id: int, on_day: date) -> None:
    conn.execute("UPDATE person SET last_notified = ? WHERE id = ?",
                 (on_day.isoformat(), person_id))
    conn.commit()
