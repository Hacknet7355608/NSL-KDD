"""
请求与响应模型。
沿用实验里 schemas.py 的写法：这里只有字段和校验规则，不碰模型、不碰文件。
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectionInput(BaseModel):
    """
    一条网络连接记录。
    features 的键必须与训练时的特征名完全一致，名单见 GET /model-info。
    protocol_type / service / flag 三个类别特征请先按 meta 里的
    categorical_encodings 编码成整数再提交。
    """

    model_config = ConfigDict(extra="forbid")

    features: dict[str, float] = Field(
        ...,
        description="特征名 -> 数值，键的数量与名称都必须与模型一致",
    )

    @field_validator("features")
    @classmethod
    def check_finite(cls, value: dict[str, float]) -> dict[str, float]:
        bad = [k for k, v in value.items() if not math.isfinite(v)]
        if bad:
            raise ValueError(f"以下特征不是有限数值：{bad}")
        return value


class PredictionResponse(BaseModel):
    """一次预测的结果。"""

    prediction: str
    confidence: float
    probabilities: dict[str, float]


class ModelInfo(BaseModel):
    """当前加载模型的身份证：回答"线上跑的是哪个模型、哪版数据、哪个 commit"。"""

    n_features: int
    classes: list[str]
    feature_names: list[str]
    mlflow_run_id: str = "unknown"
    data_version: str = "unknown"
    trained_at: str = "unknown"
    categorical_encodings: dict[str, dict[str, int]] = Field(default_factory=dict)
