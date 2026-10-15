"""Filesystem locations, overridable through environment variables."""

import os
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = Path(os.environ.get("ML_DATA_FILE", ML_ROOT.parent / "backend" / "data" / "data.xlsx"))
ARTIFACTS_DIR = Path(os.environ.get("ML_ARTIFACTS_DIR", ML_ROOT / "artifacts"))
BONUS_CONFIG_FILE = Path(os.environ.get("ML_BONUS_CONFIG", ML_ROOT / "config" / "bonus.json"))

KV_RULES_FILE = Path(os.environ.get("ML_KV_RULES", ML_ROOT / "config" / "kv_rules.json"))

KV_INPUTS_FILE = "kv_inputs.json"
PLANS_FILE = "plans.json"
METRICS_FILE = "metrics.json"
MODEL_FILE = "model.joblib"
