# bdayKeeper 🎂 (с human-in-the-loop)

Telegram-бот на [deep agents](https://docs.langchain.com/oss/python/deepagents/overview):
пишешь как человеку — «у Пети др 12 марта, любит настолки» — агент разбирает
свободный текст и ведёт список дней рождений с идеями подарков. За `LEAD_DAYS`
дней до даты бот сам напоминает.

## Human-in-the-loop

Подтверждение (`interrupt_on` в [birthday_agent/graph.py](birthday_agent/graph.py))
стоит только там, где ошибка дорого стоит:

| Инструмент | Решения | Почему |
|---|---|---|
| `delete_person` | approve / reject | удаление необратимо |

Частые безопасные операции (`add_person`, `list_upcoming`, `set_gift_idea`) идут
без подтверждения — иначе теряется лёгкость.

**Как это работает.** Когда агент вызывает инструмент из `interrupt_on`, граф
прерывается (`result.interrupts`). Бот показывает inline-кнопки. Ответ
пользователя возвращается в граф через `Command(resume={"decisions": [...]})`
(см. [main.py](main.py)). HITL требует checkpointer — паузу надо где-то хранить,
пока ждём кнопку; используется `InMemorySaver`.

Пример диалога:
```
Ты:  удали Юлю из списка
Бот: Точно удалить «Юля»? 🗑 отменить потом не выйдет
     [🗑 Удалить] [Отмена]
Ты:  (жмёшь «Удалить»)
Бот: Готово, «Юля» больше нет в списке 🗑
     Добавим кого-то ещё? Например «у Ани др 5 июля» 🎂
```

## Что внутри

```
main.py                aiogram + HITL (кнопки, Command(resume=...))
scheduler.py           ежедневная проверка дней рождений (09:00 МСК)
delivery.py            отправка напоминаний (без LLM)
db.py                  SQLite: user, person
constants.py           МСК, LEAD_DAYS, час рассылки
birthday_agent/
  graph.py             create_deep_agent + interrupt_on + checkpointer
  tools.py             add/list/set_gift/update_birthday/delete + set_reminder_schedule/set_notify_hour/show
  dates.py             общие функции дат (today_msk, parse_mmdd, days_until)
  middleware.py        одна middleware — сегодняшняя дата в промпт
  filesystem.py        память: общий свод + личный профиль на пользователя
  prompts.py, context.py, state.py
agent_memory/AGENTS.md   общий свод правил
pyproject.toml + uv.lock зависимости (uv)
.env.example             шаблон настроек
```

## Запуск

Зависимости зафиксированы в `uv.lock` (проект на [uv](https://docs.astral.sh/uv/)):

```bash
uv sync                # поставить ровно залоканные версии в .venv
cp .env.example .env   # заполни TELEGRAM_BOT_TOKEN и OPENROUTER_API_KEY
uv run python main.py
```

## Настройки (.env)

`.env` — это твои локальные секреты и параметры; он **не коммитится** (см.
`.gitignore`), поэтому в репозитории лежит только шаблон `.env.example` —
скопируй его в `.env` и заполни. Основное:

| Переменная | Что делает | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота от @BotFather | — (обязательно) |
| `OPENROUTER_API_KEY` | ключ модели | — (обязательно) |
| `AGENT_MODEL` | какая модель | `anthropic/claude-3.5-sonnet` |
| `REMIND_DAYS_BEFORE` | **дефолт** для новых пользователей: `3` или список `7,3,1` | `3` |
| `NOTIFY_HOUR` | **дефолт** часа рассылки (МСК), каждый меняет в чате | `9` |
| `BIRTHDAY_DB` | путь к базе | `birthdays.sqlite3` |

В сам день рождения бот напоминает всегда, независимо от настройки.

### Персональное расписание

`REMIND_DAYS_BEFORE` из `.env` — только значение по умолчанию. Каждый пользователь
настраивает своё расписание прямо в чате, а бот хранит его в базе (`user.remind_days`):

```
Ты:  напоминай за неделю и за день
Бот: Готово, за 7 и 1 день до ДР и в сам день ✨
Ты:  присылай в 20:00
Бот: Ок, поставил на 20:00 по Москве 👍
Ты:  как сейчас настроено?
Бот: За 7 и 1 день до ДР и в сам день, примерно в 20:00 (МСК)
```

За это отвечают `set_reminder_schedule` (за сколько дней), `set_notify_hour`
(во сколько) и `show_reminder_schedule`. Планировщик для каждой записи берёт
и дни, и час её владельца.

**Про время.** Это дневной дайджест: раз в день в выбранный час, а не будильник
на конкретную минуту. Разовых напоминаний «в 21:29» или «через 5 минут» бот не
делает — на такую просьбу он мягко объяснит и предложит настроить час. Цикл
просыпается раз в час и шлёт тем, у кого час уже наступил (если бот был выключен —
догонит в тот же день).

## Трейсинг (LangSmith)

Отдельного кода не требует — включается переменными в `.env`:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=birthday-bot
```

После этого каждый прогон агента (вызовы модели, middleware, инструменты)
виден в LangSmith в указанном проекте. `load_dotenv()` в `constants.py`
подхватывает переменные до старта агента, поэтому больше ничего не нужно.
