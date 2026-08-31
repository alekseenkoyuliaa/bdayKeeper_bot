"""Сборка агента: create_deep_agent из deepagents.

HITL включается параметром interrupt_on — как в примере из курса (m1.8_hitl.py):
- delete_person — необратимо -> approve/reject.
Остальные инструменты (add_person, list_upcoming, set_gift_idea) — без подтверждения.

interrupt_on требует checkpointer: паузу подтверждения надо где-то хранить,
пока ждём ответ пользователя. Берём InMemorySaver (живёт в процессе бота).
"""
import os

from deepagents import create_deep_agent
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from birthday_agent.context import AgentContext
from birthday_agent.filesystem import (AGENT_MEMORY, PERMISSIONS, STORE,
                                       USER_MEMORY, make_backend)
from birthday_agent.middleware import CurrentDateMiddleware
from birthday_agent.prompts import SYSTEM_PROMPT
from birthday_agent.tools import (add_person, delete_person, list_upcoming,
                                  set_gift_idea, set_notify_hour,
                                  set_reminder_schedule, show_reminder_schedule,
                                  update_birthday)

# Какие инструменты требуют подтверждения человека и какие решения разрешены.
INTERRUPT_ON = {
    "delete_person": {"allowed_decisions": ["approve", "reject"]},
}

# Из файловых инструментов агенту нужны только эти — для памяти (/memories/, /user/).
# Остальное, что deep-агент даёт по умолчанию (execute, delete, glob, grep), мы
# намеренно НЕ отдаём модели: боту дней рождений оно не нужно, а execute — это
# выполнение произвольного кода, лишняя дыра. См. security-раздел в README.
FS_TOOLS = ["ls", "read_file", "write_file", "edit_file"]


def make_model() -> ChatOpenAI:
    api_key = os.getenv("ROUTERAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("ROUTERAI_BASE_URL") or "https://openrouter.ai/api/v1"
    return ChatOpenAI(
        model=os.getenv("AGENT_MODEL", "openai/gpt-5-mini"),
        api_key=api_key,
        base_url=base_url,
    )


def build_agent():
    backend = make_backend()
    # Свой FilesystemMiddleware с урезанным набором тулов заменяет дефолтный
    # (по совпадению .name) — так модель не видит execute/delete/glob/grep.
    # _permissions передаём сюда же, т.к. этим middleware мы владеем сами.
    fs = FilesystemMiddleware(backend=backend, tools=FS_TOOLS, _permissions=PERMISSIONS)
    return create_deep_agent(
        model=make_model(),
        tools=[add_person, list_upcoming, set_gift_idea, update_birthday,
               delete_person, set_reminder_schedule, set_notify_hour,
               show_reminder_schedule],
        system_prompt=SYSTEM_PROMPT,
        middleware=[fs, CurrentDateMiddleware()],
        interrupt_on=INTERRUPT_ON,
        backend=backend,                 # инстанс, а не фабрика (deepagents 0.7)
        memory=[AGENT_MEMORY, USER_MEMORY],
        context_schema=AgentContext,
        checkpointer=InMemorySaver(),
        store=STORE,                     # долговременная память /user/ (StoreBackend)
    )
