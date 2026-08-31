"""Доставка утренних напоминаний о днях рождений в Telegram.

Без LLM: текст системный, доставка не зависит от модели — как в KindReminder.
"""
import logging

from aiogram import Bot

log = logging.getLogger("delivery")


class TelegramNotifier:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify(self, chat_id: int, name: str, days_left: int, gift_idea: str) -> None:
        when = "сегодня 🎉" if days_left == 0 else f"уже через {days_left} дн 🗓"
        gift = f"\n🎁 идея подарка: {gift_idea}" if gift_idea else ""
        await self.bot.send_message(
            chat_id,
            f"🎂 др у {name} {when}{gift}",
        )
