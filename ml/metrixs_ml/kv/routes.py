"""FastAPI routes of the АВ cabinet. Rules are re-read on change; inputs come from training artifacts."""

from __future__ import annotations

from typing import Callable
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .engine import Additions, KvDataError
from .export import build_workbook
from .recommend import recommendations
from .rules import RulesError
from .service import KvService

TAG = "АВ: моя мотивация"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SimulateRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=100)
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$", examples=["2026Q3"])
    extra_kasko: float = Field(0, ge=0, le=1e10, description="Доп. сборы КАСКО в открытом квартале, ₽")
    extra_priority: float = Field(0, ge=0, le=1e10, description="Доп. сборы приоритетных видов (ДВС кроме КАСКО), ₽")
    prolonged: int | None = Field(None, ge=0, le=100_000, description="План пролонгированных договоров в квартале, шт")
    due: int | None = Field(None, ge=0, le=100_000, description="Договоров к пролонгации, если оценка неверна, шт")

    def additions(self) -> Additions:
        return Additions(kasko=self.extra_kasko, priority=self.extra_priority, prolonged=self.prolonged, due=self.due)


def _guard(action: Callable[[], object]):
    try:
        return action()
    except KvDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RulesError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def register_kv_routes(app: FastAPI, service: Callable[[], KvService]) -> None:
    @app.get("/kv/options", tags=[TAG], summary="Агенты и кварталы", description="Список агентов и кварталов для выбора, дата расчёта.")
    def kv_options() -> dict:
        return {"success": True, "data": _guard(lambda: service().options())}

    @app.get("/kv/rules", tags=[TAG], summary="Правила АВ", description="Правила АВ из `kv_rules.json` (Решение ДРБ-УРСП-125/2019).")
    def kv_rules() -> dict:
        return {"success": True, "data": _guard(lambda: service().rules_summary())}

    @app.get("/kv/cabinet", tags=[TAG], summary="Кабинет мотивации", description="Ставки АВ по видам (база + Доп.АВ1–3) сейчас и в следующем квартале, доход, план.")
    def kv_cabinet(agent: str = Query(..., max_length=100), quarter: str = Query(..., max_length=6)) -> dict:
        return {"success": True, "data": _guard(lambda: service().cabinet(agent, quarter))}

    @app.get("/kv/recommendations", tags=[TAG], summary="Рекомендации на главную",
             description="Открытый квартал: что продлить из портфеля КАСКО и что продавать по видам и продуктам агента.")
    def kv_recommendations(agent: str = Query(..., max_length=100)) -> dict:
        return {"success": True, "data": _guard(lambda: recommendations(service(), agent))}

    @app.post("/kv/simulate", tags=[TAG], summary="Что изменится, если…", description="Пересчёт ставок и дохода при доп. продажах и пролонгациях в открытом квартале.")
    def kv_simulate(request: SimulateRequest) -> dict:
        return {"success": True, "data": _guard(lambda: service().simulate(request.agent, request.quarter, request.additions()))}

    @app.get("/kv/export", tags=[TAG], summary="Выгрузка в Excel", description="Расчёт кабинета (и сценария, если заданы доп. продажи) в .xlsx.")
    def kv_export(
        agent: str = Query(..., max_length=100),
        quarter: str = Query(..., max_length=6),
        extra_kasko: float = Query(0, ge=0, le=1e10),
        extra_priority: float = Query(0, ge=0, le=1e10),
        prolonged: int | None = Query(None, ge=0, le=100_000),
        due: int | None = Query(None, ge=0, le=100_000),
    ) -> Response:
        def build() -> bytes:
            svc = service()
            cabinet = svc.cabinet(agent, quarter)
            additions = Additions(kasko=extra_kasko, priority=extra_priority, prolonged=prolonged, due=due)
            simulation = svc.simulate(agent, quarter, additions) if additions.has_inputs() else None
            return build_workbook(cabinet, simulation)

        content = _guard(build)
        filename = quote(f"АВ_{agent}_{quarter}.xlsx")
        return Response(content, media_type=XLSX, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
