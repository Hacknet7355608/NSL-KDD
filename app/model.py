"""
模型加载与预测。
写法沿用实验里 app/database.py 的风格：一个模块、一个类、两个函数，
不做 dataclass / 依赖注入之类的抽象，读起来和课上代码一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np


class ModelNotReady(RuntimeError):
    """模型文件或元数据缺失/损坏。相当于实验里"数据库打不开"的那种错误。"""


class Predictor:
    """模型 + 元数据。feature_names 的顺序就是模型期望的输入顺序。"""

    def __init__(self, model, meta: dict):
        self.model = model
        self.meta = meta
        self.feature_names = list(meta["feature_names"])
        self.classes = [str(c) for c in model.classes_]

    def predict(self, features: dict[str, float]) -> dict:
        # sklearn 只认列的顺序、不认列名：按 feature_names 排好，再变成一行二维数组
        row = np.array([[features[name] for name in self.feature_names]], dtype="float64")
        proba = self.model.predict_proba(row)[0]
        best = int(np.argmax(proba))
        return {
            "prediction": self.classes[best],
            "confidence": round(float(proba[best]), 4),
            "probabilities": {c: round(float(p), 4) for c, p in zip(self.classes, proba)},
        }


def load_predictor(model_path: str | Path, meta_path: str | Path) -> Predictor:
    model_path, meta_path = Path(model_path), Path(meta_path)
    if not model_path.is_file():
        raise ModelNotReady(f"模型文件不存在：{model_path}（应由 A 同学训练后导出）")
    if not meta_path.is_file():
        raise ModelNotReady(f"模型元数据不存在：{meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelNotReady(f"model_meta.json 不是合法 JSON：{exc}") from exc
    names = meta.get("feature_names") or []
    if not names:
        raise ModelNotReady("model_meta.json 缺少 feature_names，无法保证特征顺序")
    model = joblib.load(model_path)
    expected = getattr(model, "n_features_in_", len(names))
    if expected != len(names):
        raise ModelNotReady(f"模型期望 {expected} 个特征，但 meta 里写了 {len(names)} 个")
    return Predictor(model, meta)
