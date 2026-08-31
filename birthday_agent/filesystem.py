"""Файловая система агента: память + черновики.

deepagents 0.7 убрал backend-фабрики (backend теперь — готовый инстанс), поэтому
разделение по пользователю делаем современным способом — через namespace у
StoreBackend (ровно тот механизм контроля доступа по пользователю из документации).

- /memories/ — общий свод на всех, читается с диска (agent_memory/AGENTS.md).
- /user/     — личный профиль; StoreBackend с namespace=(user_id,) физически
               изолирует данные разных пользователей.
- default    — StateBackend: черновики живут в state диалога.

Писать разрешено только в два файла памяти (PERMISSIONS), остальное — deny.
"""
from pathlib import Path

from deepagents import FilesystemPermission
from deepagents.backends import (CompositeBackend, FilesystemBackend,
                                  StateBackend, StoreBackend)
from langgraph.store.memory import InMemoryStore

MEMORY_DIR = Path(__file__).resolve().parent.parent / "agent_memory"

AGENT_MEMORY = "/memories/AGENTS.md"
USER_MEMORY = "/user/PROFILE.md"

PERMISSIONS = [
    FilesystemPermission(operations=["read", "write"],
                         paths=[AGENT_MEMORY, USER_MEMORY], mode="allow"),
    FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
]

# Долговременная память между диалогами. В проде — Postgres/Redis-реализация
# BaseStore; для локального запуска хватает InMemoryStore.
STORE = InMemoryStore()


def make_backend() -> CompositeBackend:
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": FilesystemBackend(root_dir=MEMORY_DIR, virtual_mode=True),
            "/user/": StoreBackend(
                namespace=lambda rt: (str(rt.context.user_id),),
                store=STORE,
            ),
        },
    )
