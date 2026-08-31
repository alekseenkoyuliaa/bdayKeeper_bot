"""Работа с датами дней рождений — общее место для инструментов и планировщика.

Дата рождения хранится как «MM-DD» (год не важен, повод повторяется каждый год).
Единый «сегодня» — по Москве, чтобы приём и рассылка считали одинаково.
"""
from datetime import date, datetime

from constants import MSK


def today_msk() -> date:
    """Сегодня по Москве — единый источник «сегодня» для всего бота."""
    return datetime.now(MSK).date()


def parse_mmdd(value: str) -> str | None:
    """Принять 'MM-DD' (или 'YYYY-MM-DD') и вернуть нормализованное 'MM-DD'."""
    parts = value.strip().split("-")
    if len(parts) == 3:  # YYYY-MM-DD
        parts = parts[1:]
    if len(parts) != 2:
        return None
    try:
        m, d = int(parts[0]), int(parts[1])
        date(2000, m, d)  # проверка валидности (2000 — високосный, 29.02 пройдёт)
    except ValueError:
        return None
    return f"{m:02d}-{d:02d}"


def days_until(mmdd: str, today: date) -> int:
    """Сколько дней до ближайшего наступления даты 'MM-DD' от `today`."""
    m, d = (int(x) for x in mmdd.split("-"))
    try:
        nxt = date(today.year, m, d)
    except ValueError:  # 29 февраля в невисокосный год -> считаем как 1 марта
        nxt = date(today.year, 3, 1)
    if nxt < today:
        try:
            nxt = date(today.year + 1, m, d)
        except ValueError:
            nxt = date(today.year + 1, 3, 1)
    return (nxt - today).days
