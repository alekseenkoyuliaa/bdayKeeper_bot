"""Зависимости и идентичность одного вызова агента.

Это то, что инструменты получают ОТ ПРИЛОЖЕНИЯ, а не от модели: модель не может
подделать user_id и не имеет прямого доступа к базе.
"""
import sqlite3

from pydantic import BaseModel, ConfigDict, Field


class AgentContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    conn: sqlite3.Connection = Field(description="Соединение SQLite процесса")
    user_id: int = Field(description="Telegram id пользователя, от чьего имени идёт вызов")
