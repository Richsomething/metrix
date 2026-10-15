"""Agency reward (АВ/КВ) rules from ml/config/kv_rules.json, reloaded when the file changes — no retraining needed.

Source: Решение ДРБ-УРСП-125/2019 and the operational АВ calculator. Bands are lists of
[upper_bound_exclusive, value]: the value applies while x < bound; a null bound closes the scale.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Band = tuple[float | None, float]


class RulesError(ValueError):
    """Rules are missing, invalid or do not cover the requested period."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LineRule(_Frozen):
    title: str
    priority: bool  # «приоритетный» вид: все ДВС, кроме КАСКО
    base_rate: float | None = Field(default=None, ge=0, le=1)
    max_bonus: float | None = Field(default=None, ge=0, le=1)  # cap on Доп.АВ1 + Доп.АВ2 + Доп.АВ3
    note: str | None = None


class KaskoRule(_Frozen):
    line: str
    scale_by_group: dict[str, list[Band]]
    newcomer_rate: float = Field(ge=0, le=1)
    cap: float = Field(ge=0, le=1)
    group_aliases: dict[str, str] = {}  # data group name → scale group (an assumption, see note)
    group_aliases_note: str | None = None

    def scale_group(self, group: str | None) -> str | None:
        return None if group is None else self.group_aliases.get(group, group)


class DynamicsRule(_Frozen):
    floor_base: float = Field(ge=0)
    bands_by_reporting_quarter: dict[Literal["1", "2", "3", "4"], list[Band]]


class PenetrationRule(_Frozen):
    above: float = Field(ge=0, le=1)  # strictly greater than
    bonus: float = Field(ge=0, le=1)


class ProlongationRule(_Frozen):
    at_least: float = Field(ge=0, le=1)
    bonus: float = Field(ge=0, le=1)
    lines: list[str] | None = None  # lines whose contracts count; None = every contract of the list
    exclude_products: dict[str, list[str]] = {}  # line → products that do not count

    def counts(self, line: str, product: str) -> bool:
        return (self.lines is None or line in self.lines) and product not in self.exclude_products.get(line, [])
    note: str


class Scenarios(_Frozen):
    cautious: float = Field(ge=-1, le=0)
    optimistic: float = Field(ge=0, le=1)
    note: str


def band_value(bands: list[Band], x: float) -> tuple[float, int]:
    """Value of the band containing x (x < bound) and its index."""
    for index, (bound, value) in enumerate(bands):
        if bound is None or x < bound:
            return value, index
    return bands[-1][1], len(bands) - 1


class RuleVersion(_Frozen):
    id: str
    status: Literal["demo", "approved"]
    title: str
    source: str
    valid_from: date
    valid_to: date | None = None
    excluded_branches: list[str] = []
    lines: dict[str, LineRule]
    kasko: KaskoRule
    dynamics: DynamicsRule
    penetration: PenetrationRule
    prolongation: ProlongationRule
    scenarios: Scenarios

    @model_validator(mode="after")
    def _consistent(self) -> "RuleVersion":
        if self.kasko.line not in self.lines or self.lines[self.kasko.line].priority:
            raise ValueError("линия КАСКО должна быть описана и не быть приоритетной")
        for name, bands in [*self.kasko.scale_by_group.items(), *self.dynamics.bands_by_reporting_quarter.items()]:
            bounds = [b for b, _ in bands]
            if not bands or bounds[-1] is not None or any(b is None for b in bounds[:-1]):
                raise ValueError(f"шкала «{name}»: последняя граница null, остальные заданы")
            if bounds[:-1] != sorted(bounds[:-1]):
                raise ValueError(f"шкала «{name}»: границы по возрастанию")
        return self

    def line(self, name: str) -> LineRule:
        # an unknown line is a voluntary type without a known rate: counted in ДВС, no АВ computed
        return self.lines.get(name) or LineRule(title=name.title(), priority=True, base_rate=None, note="Линия не описана в правилах")

    def covers(self, quarter: pd.Period) -> bool:
        start = quarter.start_time.date()
        return self.valid_from <= start and (self.valid_to is None or start <= self.valid_to)


class RuleBook(_Frozen):
    versions: list[RuleVersion] = Field(min_length=1)

    def for_quarter(self, quarter: pd.Period) -> RuleVersion:
        matching = [v for v in self.versions if v.covers(quarter)]
        if not matching:
            raise RulesError(f"Нет правил АВ, действующих в {quarter.year}Q{quarter.quarter}")
        return max(matching, key=lambda v: v.valid_from)


class RulesCache:
    """Re-reads the rules file only when its modification time changes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._book: RuleBook | None = None

    def get(self) -> tuple[RuleBook, float]:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError as exc:
            raise RulesError(f"Не найден файл правил АВ: {self.path}") from exc
        with self._lock:
            if self._book is None or mtime != self._mtime:
                try:
                    self._book = RuleBook.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
                except (ValidationError, json.JSONDecodeError) as exc:
                    raise RulesError(f"Ошибка в правилах АВ: {exc}") from exc
                self._mtime = mtime
            return self._book, mtime
