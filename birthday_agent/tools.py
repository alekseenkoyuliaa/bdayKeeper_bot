"""Инструменты агента.

Каждый достаёт из runtime.context то, что дало приложение (user_id, conn) —
модель этим не управляет. Инструмент delete_person перечислен в interrupt_on
(см. graph.py): перед его выполнением платформа спросит подтверждение у человека.
Сам инструмент про подтверждение ничего не знает — HITL живёт снаружи.
"""
from langchain.tools import ToolRuntime, tool

import db
from birthday_agent.context import AgentContext
from birthday_agent.dates import days_until, parse_mmdd, today_msk


@tool
async def add_person(name: str, birthday: str, gift_idea: str = "",
                     runtime: ToolRuntime[AgentContext] = None) -> str:
    """Записать человека и его день рождения.
    name: чьё день рождения.
    birthday: дата в формате MM-DD (например 03-12).
    gift_idea: необязательная идея подарка.
    """
    mmdd = parse_mmdd(birthday)
    if mmdd is None:
        return "Ошибка: дату дай в формате MM-DD, например 03-12."
    ctx = runtime.context
    if db.find_person(ctx.conn, ctx.user_id, name):
        return (f"{name} уже в списке. Чтобы поменять дату — update_birthday, "
                f"подарок — set_gift_idea.")
    db.add_person(ctx.conn, ctx.user_id, name, mmdd, gift_idea)
    tail = f", идея подарка: {gift_idea}" if gift_idea else ""
    return f"Запомнил: {name}, день рождения {mmdd}{tail}."


@tool
async def list_upcoming(days: int = 30, runtime: ToolRuntime[AgentContext] = None) -> str:
    """Показать, у кого день рождения в ближайшие `days` дней (по умолчанию 30)."""
    ctx = runtime.context
    today = today_msk()
    rows = db.list_people(ctx.conn, ctx.user_id)
    items = []
    for r in rows:
        left = days_until(r["birthday"], today)
        if left <= days:
            items.append((left, r))
    if not items:
        return f"В ближайшие {days} дней дней рождений нет."
    items.sort(key=lambda x: x[0])
    lines = []
    for left, r in items:
        when = "сегодня!" if left == 0 else f"через {left} дн."
        gift = f" — подарок: {r['gift_idea']}" if r["gift_idea"] else ""
        lines.append(f"{r['name']} ({r['birthday']}), {when}{gift}")
    return "\n".join(lines)


@tool
async def set_gift_idea(name: str, gift_idea: str,
                        runtime: ToolRuntime[AgentContext] = None) -> str:
    """Сохранить или обновить идею подарка для человека."""
    ctx = runtime.context
    if db.set_gift_idea(ctx.conn, ctx.user_id, name, gift_idea):
        return f"Идея подарка для {name}: {gift_idea}."
    return f"{name} не найден в списке. Сначала добавь его."


@tool
async def update_birthday(name: str, new_birthday: str,
                          runtime: ToolRuntime[AgentContext] = None) -> str:
    """Изменить дату рождения человека, который уже есть в списке.
    new_birthday: новая дата в формате MM-DD (например 07-05).
    """
    mmdd = parse_mmdd(new_birthday)
    if mmdd is None:
        return "Ошибка: дату дай в формате MM-DD, например 07-05."
    ctx = runtime.context
    if db.update_birthday(ctx.conn, ctx.user_id, name, mmdd):
        return f"Обновил дату: {name} теперь {mmdd}."
    return f"{name} не найден в списке. Сначала добавь его."


@tool
async def delete_person(name: str, runtime: ToolRuntime[AgentContext] = None) -> str:
    """Удалить человека из списка. Необратимо.
    (Стоит за подтверждением человека — см. interrupt_on.)
    """
    ctx = runtime.context
    if db.delete_person(ctx.conn, ctx.user_id, name):
        return f"{name} удалён из списка."
    return f"{name} не найден в списке."


def _schedule_phrase(days: list[int]) -> str:
    if not days:
        return "напоминаю только в сам день рождения"
    return "напоминаю за " + ", ".join(str(d) for d in days) + " дн. до ДР и в сам день"


@tool
async def set_reminder_schedule(days_before: str,
                                runtime: ToolRuntime[AgentContext] = None) -> str:
    """Настроить, за сколько дней ДО дня рождения напоминать этому пользователю.
    days_before: число или список через запятую, например "7" или "7,3,1".
        Чтобы напоминать только в сам день рождения — передай "0".
    В сам день рождения напоминание приходит всегда, независимо от настройки.
    """
    ctx = runtime.context
    # только положительные числа; повторы убираем, сортируем по убыванию
    nums = sorted({int(p.strip()) for p in days_before.split(",")
                   if p.strip().isdigit() and int(p.strip()) > 0}, reverse=True)
    raw = ",".join(str(n) for n in nums) if nums else "none"
    db.set_remind_days(ctx.conn, ctx.user_id, raw)
    return "Готово — " + _schedule_phrase(nums) + "."


@tool
async def set_notify_hour(hour: int, runtime: ToolRuntime[AgentContext] = None) -> str:
    """Во сколько (час по Москве, 0..23) присылать этому пользователю напоминания.
    Напоминания — это дневной дайджест в выбранный час, а не будильник на минуту.
    """
    if not 0 <= hour <= 23:
        return "Ошибка: час должен быть от 0 до 23."
    ctx = runtime.context
    db.set_notify_hour(ctx.conn, ctx.user_id, hour)
    return f"Готово — буду присылать напоминания около {hour:02d}:00 по Москве."


@tool
async def show_reminder_schedule(runtime: ToolRuntime[AgentContext] = None) -> str:
    """Показать текущее расписание напоминаний этого пользователя (дни + час)."""
    ctx = runtime.context
    days = db.get_remind_days(ctx.conn, ctx.user_id)
    hour = db.get_notify_hour(ctx.conn, ctx.user_id)
    return f"Сейчас {_schedule_phrase(days)}, присылаю около {hour:02d}:00 (МСК)."
