"""Планировщик дней рождений.

Каждый пользователь выбирает СВОЙ час рассылки (db.get_notify_hour) и своё
расписание «за сколько дней» (db.get_remind_days). Поэтому цикл просыпается раз в
час и проверяет всех: пользователю шлём, если текущий час уже >= его часа рассылки
(так переживаем простой бота — если проспали момент, догоним в тот же день) и
запись ещё не отправлялась сегодня (last_notified). Это дневной дайджест, а не
будильник на конкретную минуту.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import db
from birthday_agent.dates import days_until
from constants import MSK

log = logging.getLogger("scheduler")


def _seconds_until_next_hour() -> float:
    now = datetime.now(MSK)
    nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (nxt - now).total_seconds()


class Scheduler:
    def __init__(self, conn):
        self.conn = conn

    async def _scan_and_notify(self, notifier) -> None:
        now = datetime.now(MSK)
        today = now.date()
        for p in db.all_people(self.conn):
            if p["last_notified"] == today.isoformat():
                continue  # уже слали сегодня
            if now.hour < db.get_notify_hour(self.conn, p["user_id"]):
                continue  # для этого пользователя ещё не наступил его час
            left = days_until(p["birthday"], today)
            if left == 0 or left in db.get_remind_days(self.conn, p["user_id"]):
                chat_id = db.get_chat_id(self.conn, p["user_id"]) or p["user_id"]
                try:
                    await notifier.notify(chat_id, p["name"], left, p["gift_idea"])
                    db.mark_notified(self.conn, p["id"], today)
                except Exception:
                    log.exception("notify failed for person id=%s", p["id"])

    async def run(self, notifier) -> None:
        log.info("scheduler started")
        # Прогон сразу на старте — вдруг час уже наступил и сегодня есть что слать.
        await self._scan_and_notify(notifier)
        while True:
            await asyncio.sleep(_seconds_until_next_hour())
            await self._scan_and_notify(notifier)
