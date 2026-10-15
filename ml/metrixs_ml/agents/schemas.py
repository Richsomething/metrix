"""Structured outputs of the agents and the reports the API returns."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Analysis(BaseModel):
    summary: str = Field(description="2–4 предложения: как агент отработал квартал относительно плана")
    strengths: list[str] = Field(description="Сильные стороны квартала, с цифрами из инструментов")
    risks: list[str] = Field(description="Риски и слабые места, с цифрами из инструментов")
    plan_drivers: list[str] = Field(description="Главные факторы, из которых сложился план")


class MotivationLetter(BaseModel):
    title: str = Field(description="Короткий заголовок письма")
    body: str = Field(description="Текст письма агенту, 120–250 слов")
    next_steps: list[str] = Field(description="2–4 конкретных шага на следующий квартал с целевыми суммами")


class AuditVerdict(BaseModel):
    approved: bool = Field(description="true, если все цифры и утверждения письма подтверждаются фактами")
    issues: list[str] = Field(description="Найденные расхождения; пустой список, если всё верно")


class ToolCall(BaseModel):
    role: str
    name: str
    input: dict


class ModelUse(BaseModel):
    role: str
    model: str
    fallback_reason: str | None = None


class ReviewReport(BaseModel):
    agent: str
    quarter: str
    bonus: dict = Field(description="Детерминированный расчёт премии за завершённый квартал — источник истины")
    analysis: Analysis
    letter: MotivationLetter
    audit: AuditVerdict
    revisions: int
    tool_calls: list[ToolCall]
    models: list[ModelUse]


class KvReviewReport(BaseModel):
    agent: str
    quarter: str
    calculation: dict = Field(description="Детерминированный расчёт АВ — источник истины для цифр")
    analysis: Analysis
    letter: MotivationLetter
    audit: AuditVerdict
    revisions: int
    tool_calls: list[ToolCall]
    models: list[ModelUse]


class AskReport(BaseModel):
    answer: str
    tool_calls: list[ToolCall]
    models: list[ModelUse]
