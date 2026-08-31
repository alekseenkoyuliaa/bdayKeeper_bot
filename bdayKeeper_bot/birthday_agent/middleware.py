"""Единственная middleware агента: сообщает модели сегодняшнюю дату.

Без неё модель не сможет корректно понять «через 3 дня» или «в этом месяце».
Дата фиксируется один раз на запуск (before_agent), чтобы все вызовы модели
внутри одного запроса видели одинаковое «сегодня».

Повторяет приём CurrentTimeMiddleware из KindReminder, но для даты.
"""
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from constants import MSK
from birthday_agent.state import CurrentDateState


class CurrentDateMiddleware(AgentMiddleware[CurrentDateState]):
    state_schema = CurrentDateState

    async def abefore_agent(self, state: CurrentDateState, runtime: Runtime[None]) -> dict[str, Any]:
        today = datetime.now(MSK).date().isoformat()
        return {"current_date": today}

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        today = request.state["current_date"]
        request = request.override(system_message=SystemMessage(
            f"{request.system_prompt}\n\n"
            f"Сегодня {today} (московское время). Даты рождения храни как «MM-DD»."
        ))
        return await handler(request)
