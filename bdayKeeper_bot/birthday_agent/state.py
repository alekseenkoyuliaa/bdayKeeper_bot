"""Расширение state deep-агента для middleware."""
from langchain.agents.middleware import AgentState


class CurrentDateState(AgentState):
    """Сегодняшняя дата, зафиксированная на один запуск агента."""

    current_date: str | None
