"""Telegram-бот дней рождений с human-in-the-loop.

Обычные запросы обрабатываются сразу. Но если агент захотел вызвать инструмент
из interrupt_on (delete_person), граф прерывается (result.interrupts), и мы
показываем пользователю кнопки. Ответ пользователя возвращается в граф через
Command(resume={"decisions": [...]}) — ровно как в примере курса m1.8_hitl.py,
только input() заменён на inline-кнопки Telegram.
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)
from dotenv import load_dotenv
from langgraph.types import Command

import db
from birthday_agent import AgentContext, build_agent
from delivery import TelegramNotifier
from scheduler import Scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("main")

DB_PATH = os.getenv("BIRTHDAY_DB", "birthdays.sqlite3")

# Список разрешённых chat_id (через запятую). Пусто -> бот открыт всем.
# Каждый запрос к боту тратит токены модели на ТВОЙ ключ, поэтому в проде
# лучше ограничить круг тех, кто может пользоваться ботом.
ALLOWED = {int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip().isdigit()}

dp = Dispatcher()

# Незавершённые подтверждения, по пользователю. Хранит action_requests из
# прерывания — чтобы построить кнопки и понять, что подтверждаем.
PENDING: dict[int, list[dict]] = {}


def _allowed(user_id: int) -> bool:
    return not ALLOWED or user_id in ALLOWED


def _config(user_id: int) -> dict:
    return {"configurable": {"thread_id": str(user_id)}}


def _reply_text(value) -> str:
    msg = value["messages"][-1]
    return getattr(msg, "text", None) or getattr(msg, "content", None) or "Готово ✨"


def _describe(req: dict) -> str:
    """Человеческий вопрос-подтверждение под конкретное действие."""
    if req["name"] == "delete_person":
        name = req["args"].get("name", "эту запись")
        return f"Точно удалить «{name}»? 🗑 отменить потом не выйдет"
    # запасной вариант для будущих действий
    args = ", ".join(f"{k}: {v}" for k, v in req["args"].items())
    return f"Подтвердить «{req['name']}»?\n{args}"


def _keyboard(req: dict) -> InlineKeyboardMarkup:
    confirm = "🗑 Удалить" if req["name"] == "delete_person" else "✅ Подтвердить"
    row = [
        InlineKeyboardButton(text=confirm, callback_data="hitl:approve"),
        InlineKeyboardButton(text="Отмена", callback_data="hitl:reject"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _invoke(agent, conn, user_id: int, payload):
    """Прогнать граф (вход или Command(resume=...)) и вернуть результат.

    user_id передаём явно: в callback'е message.from_user — это БОТ, а thread_id
    прерывания привязан к id пользователя, поэтому resume должен идти под ним же.
    """
    return await agent.ainvoke(
        payload,
        config=_config(user_id),
        context=AgentContext(conn=conn, user_id=user_id),
        version="v2",
    )


async def _present(message: Message, user_id: int, result) -> None:
    """Показать результат: либо запрос подтверждения с кнопками, либо ответ текстом."""
    if result.interrupts:
        reqs = result.interrupts[0].value["action_requests"]
        PENDING[user_id] = reqs
        await message.answer(_describe(reqs[0]), reply_markup=_keyboard(reqs[0]))
    else:
        PENDING.pop(user_id, None)
        await message.answer(_reply_text(result.value))


async def _run(agent, conn, message: Message, payload) -> None:
    uid = message.from_user.id
    await _present(message, uid, await _invoke(agent, conn, uid, payload))


@dp.message(CommandStart())
async def cmd_start(message: Message, conn) -> None:
    u = message.from_user
    if not _allowed(u.id):
        log.info("rejected unauthorized user_id=%s", u.id)
        await message.answer("Извини, этот бот доступен только своим 🙈")
        return
    db.ensure_user(conn, u.id, u.full_name, message.chat.id)
    await message.answer(
        "Привет! 🎂 я помню дни рождения и подскажу идеи подарков\n\n"
        "Просто пиши как другу:\n"
        "• «у Пети др 12 марта, любит настолки»\n"
        "• «у кого скоро др?»\n"
        "• «напоминай за неделю» — настрой, когда пинговать ✨")


@dp.message(F.text)
async def on_message(message: Message, agent, conn) -> None:
    u = message.from_user
    if not _allowed(u.id):
        log.info("rejected unauthorized user_id=%s", u.id)
        await message.answer("Извини, этот бот доступен только своим 🙈")
        return
    db.ensure_user(conn, u.id, u.full_name, message.chat.id)

    if u.id in PENDING:
        await message.answer("Секунду, ответь сначала на вопрос выше кнопками 👆")
        return

    try:
        await _run(agent, conn, message, {"messages": [{"role": "user", "content": message.text}]})
    except Exception:
        log.exception("agent failed, user_id=%s", u.id)
        await message.answer("Ой, что-то пошло не так 😅 давай ещё разок")


@dp.callback_query(F.data.startswith("hitl:"))
async def on_decision(cb: CallbackQuery, agent, conn) -> None:
    u = cb.from_user
    reqs = PENDING.get(u.id)
    if not reqs:
        await cb.answer("Запрос уже неактуален.")
        return
    choice = cb.data.split(":", 1)[1]
    req = reqs[0]
    tool, name = req["name"], req["args"].get("name")

    # approve / reject применяем ко всем заявкам этого прерывания.
    if choice == "approve":
        decisions = [{"type": "approve"} for _ in reqs]
    else:
        decisions = [{"type": "reject", "message": "Пользователь отклонил действие."}
                     for _ in reqs]

    PENDING.pop(u.id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer()

    result = await _invoke(agent, conn, u.id,
                           Command(resume={"decisions": decisions}))
    if result.interrupts:  # вдруг дальше ещё одно подтверждение
        await _present(cb.message, u.id, result)
        return

    # Человеческий ответ после удаления (не полагаемся на формулировку модели).
    if tool == "delete_person":
        if choice == "approve" and db.find_person(conn, u.id, name) is None:
            await cb.message.answer(
                f"Готово, «{name}» больше нет в списке 🗑\n\n"
                f"Добавим кого-то ещё? Например «у Ани др 5 июля» 🎂")
        elif choice == "reject":
            await cb.message.answer(f"Окей, «{name}» остаётся на месте 👌")
        else:  # approve, но удалить не вышло (не нашёлся) — отдадим ответ модели
            await cb.message.answer(_reply_text(result.value))
    else:
        await _present(cb.message, u.id, result)


async def main() -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")

    bot = Bot(bot_token)
    conn = db.connect(DB_PATH)
    agent = build_agent()
    sched = Scheduler(conn)
    notifier = TelegramNotifier(bot)

    scheduler_task = asyncio.create_task(sched.run(notifier))
    log.info("бот запущен, шедулер крутится")
    try:
        # conn и agent прокидываются в хендлеры через DI (по имени параметра)
        await dp.start_polling(bot, agent=agent, conn=conn)
    finally:
        scheduler_task.cancel()
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
