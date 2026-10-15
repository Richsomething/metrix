"""Train, backtest and export plans.

    python -m metrixs_ml.train [--data PATH] [--out DIR] [--as-of YYYY-MM-DD]

Only quarters that ended on or before --as-of (default: today) count as completed; later records
are excluded from training, backtest and bonuses.

Writes to the artifacts directory:
  metrics.json  — backtest scores of every candidate, the chosen model, data cutoff
  plans.json    — recommended plans: out-of-sample for completed quarters + forecast for the next one
  model.joblib  — chosen model fitted on all completed quarters
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import settings
from .backtest import compare, walk_forward
from .data import cut_off, load_raw
from .features import FEATURE_LABELS, FEATURES, build_frame, has_features, quarter_label
from .kv.inputs import build_kv_inputs, round_floats
from .models import candidate_factories, labelled

log = logging.getLogger("metrixs_ml.train")

DATASET_NOTE = "Синтетический обезличенный набор; точность на реальных данных не установлена."
# No approved (management-set) plans exist in the export, so bonuses are computed against the recommended plan.
BONUS_BASIS = "recommended_plan"


def _contributions(items: list[tuple[str, float]]) -> list[dict]:
    return [{"key": key, "label": FEATURE_LABELS.get(key, key), "value": round(value, 2)} for key, value in items]


def _plan_rows(predictions: pd.DataFrame, kind: str) -> list[dict]:
    is_forecast = kind == "forecast"
    return [
        {
            "agent": r.agent,
            "quarter": r.quarter_label,
            "kind": kind,
            "isForecast": is_forecast,
            "recommendedPlan": round(float(r.plan), 2),
            "approvedPlan": None,
            "bonusBasis": None if is_forecast else BONUS_BASIS,
            "fact": None if is_forecast else round(float(r.fact), 2),
            "refundShare": None if is_forecast or pd.isna(r.refund_share) else round(float(r.refund_share), 4),
            "contributions": _contributions(r.contributions),
        }
        for r in predictions.itertuples()
    ]


def _feature_importance(model, frame: pd.DataFrame) -> list[dict]:
    """Mean |contribution| in money across known quarters; empty for models without features."""
    rows = labelled(frame)
    if not hasattr(model, "background") or rows.empty:
        return []
    contributions = pd.DataFrame([dict(c) for c in model.explain(rows)])[FEATURES]
    importance = contributions.abs().mean().sort_values(ascending=False)
    return [{"key": k, "label": FEATURE_LABELS[k], "value": round(float(v), 2)} for k, v in importance.items()]


def run(data_path: Path, out_dir: Path, as_of: date) -> dict:
    log.info("Читаю %s (дата отчёта %s)", data_path, as_of)
    raw = load_raw(data_path)
    cutoff = cut_off(raw, pd.Timestamp(as_of))
    log.info("Исключено записей незавершённых кварталов: %d", cutoff.excluded_rows)

    frame = build_frame(cutoff.raw, horizon=1)
    factories = candidate_factories()

    scores = compare(frame, factories)
    best = scores[0]
    log.info("Бэктест WAPE (синтетический набор): %s", ", ".join(f"{s.name}={s.wape:.4%}" for s in scores))
    log.info("Выбрана модель: %s", best.title)

    history = walk_forward(frame, factories[best.name], explain=True)

    final_model = factories[best.name]().fit(frame)
    future = frame[frame["fact"].isna() & frame["lag1"].notna() & has_features(frame)]
    forecast = future.assign(plan=final_model.predict(future), contributions=final_model.explain(future))

    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataFile": data_path.name,
        "datasetNote": DATASET_NOTE,
        "asOf": as_of.isoformat(),
        "lastCompletedQuarter": quarter_label(cutoff.last_completed_quarter),
        "futureRowsExcluded": cutoff.excluded_rows,
        "chosen": best.name,
        "scores": [asdict(s) for s in scores],
        "plannedQuarters": sorted(history["quarter_label"].unique().tolist()),
        "forecastQuarter": forecast["quarter_label"].iloc[0] if not forecast.empty else None,
        "bonusBasis": BONUS_BASIS,
        "featureImportance": _feature_importance(final_model, frame),
        "agents": sorted(frame["agent"].unique().tolist()),
    }
    plans = _plan_rows(history, "completed") + _plan_rows(forecast, "forecast")

    (out_dir / settings.METRICS_FILE).write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / settings.PLANS_FILE).write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")
    joblib.dump(final_model, out_dir / settings.MODEL_FILE)

    # АВ inputs: facts, the running quarter (only contracts signed by as_of) and the next-quarter forecast.
    kv_inputs = round_floats(build_kv_inputs(data_path, pd.Timestamp(as_of)))
    (out_dir / settings.KV_INPUTS_FILE).write_text(json.dumps(kv_inputs, ensure_ascii=False), encoding="utf-8")
    chosen = kv_inputs["forecastQuality"]["chosen"]
    log.info("АВ: прогноз сборов — %s, WAPE %.1f%% (синтетика)", chosen["method"], (chosen["wape"] or 0) * 100)
    log.info("Артефакты сохранены в %s (%d планов)", out_dir, len(plans))
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение модели рекомендуемого плана и выгрузка планов")
    parser.add_argument("--data", type=Path, default=settings.DATA_FILE)
    parser.add_argument("--out", type=Path, default=settings.ARTIFACTS_DIR)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="Дата отчёта, ГГГГ-ММ-ДД")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    np.seterr(all="ignore")
    run(args.data, args.out, args.as_of)


if __name__ == "__main__":
    main()
