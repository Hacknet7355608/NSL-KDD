"""
测试夹具：用随机数据现场训一个小模型。
好处：CI 不需要下载 19MB 数据集，也不需要 A 同学先把模型提交上来，
但走的仍然是真实的 sklearn + joblib + model_meta.json 代码路径。
写法照搬实验里的 conftest.py：给 client 一个自己的"数据源"（这里是模型目录）。
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestClassifier

from app.main import create_app

FEATURES = ("duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes")
CLASSES = ("DoS", "Probe", "R2L", "U2R", "normal")


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("model")
    rng = np.random.default_rng(0)
    rows = 300
    X = rng.normal(size=(rows, len(FEATURES)))
    y = np.array([CLASSES[i % len(CLASSES)] for i in range(rows)])
    model = RandomForestClassifier(n_estimators=10, random_state=42).fit(X, y)
    joblib.dump(model, directory / "model.joblib", compress=3)
    meta = {
        "feature_names": list(FEATURES),
        "classes": [str(c) for c in model.classes_],
        "mlflow_run_id": "test-run-id",
        "data_version": "0" * 32,
        "trained_at": "2026-01-01T00:00:00+00:00",
        "categorical_encodings": {"protocol_type": {"icmp": 0, "tcp": 1, "udp": 2}},
    }
    (directory / "model_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return directory


@pytest.fixture()
def client(model_dir: Path):
    # 与实验里 TestClient(create_app(database_path)) 完全一致：
    # 每个测试拿到自己的 app 实例，模型路径由测试自己指定
    with TestClient(create_app(model_dir / "model.joblib", model_dir / "model_meta.json")) as c:
        yield c


@pytest.fixture()
def payload() -> dict:
    return {"features": {name: 0.0 for name in FEATURES}}
