"""Общие константы: часовой пояс и настройки рассылки.

Значения читаются из окружения (.env), поэтому load_dotenv здесь — чтобы
константы были доступны и при импорте до main (напр. в планировщике).
"""
import os
from datetime import timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

# Всё считаем по Москве.
MSK = timezone(timedelta(hours=3))


def _parse_days(raw: str) -> list[int]:
    """'3' -> [3];  '7,3,1' -> [7, 3, 1]. Мусор игнорируем, дефолт — [3]."""
    days = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0 and int(part) not in days:
            days.append(int(part))
    return sorted(days, reverse=True) or [3]


# За сколько дней до дня рождения напоминать. Настраивается через .env:
#   REMIND_DAYS_BEFORE=3      — напомнить за 3 дня
#   REMIND_DAYS_BEFORE=7,3,1  — напомнить за 7, за 3 и за 1 день
# В сам день рождения бот напоминает всегда, независимо от этого списка.
LEAD_DAYS = _parse_days(os.getenv("REMIND_DAYS_BEFORE", "3"))

# В котором часу (МСК) слать утреннюю проверку дней рождений.
NOTIFY_HOUR = int(os.getenv("NOTIFY_HOUR", "9"))
