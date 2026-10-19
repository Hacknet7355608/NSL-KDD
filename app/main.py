"""FastAPI 服务入口。
沿用实验里的 create_app() 工厂写法：
    app = create_app(模型路径, 元数据路径)
测试传临时模型，线上用环境变量或默认的 models/ 目录，互不干扰。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.model import ModelNotReady, Predictor, load_predictor
from app.schemas import ConnectionInput, ModelInfo, PredictionResponse
from app.settings import get_settings, validate_for_env


def create_app(model_path=None, meta_path=None) -> FastAPI:
    settings = get_settings()
    validate_for_env(settings)

    model_file = Path(model_path or settings.model_path).resolve()
    meta_file = Path(meta_path or settings.model_meta_path).resolve()

    application = FastAPI(
        title="NSL-KDD 网络入侵检测 API",
        version="1.0.0",
        description="输入一条网络连接的特征，输出 normal / DoS / Probe / R2L / U2R 五分类结果。",
    )

    state = {"predictor": None}

    def get_predictor() -> Predictor:
        """第一次请求时加载模型；加载失败抛 503，而不是让整个进程起不来。"""
        if state["predictor"] is None:
            try:
                state["predictor"] = load_predictor(model_file, meta_file)
            except ModelNotReady as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        return state["predictor"]

    @application.get("/", tags=["meta"])
    def root() -> dict:
        return {"service": "nsl-kdd", "version": application.version, "docs": "/docs"}

    @application.get("/health", tags=["meta"])
    def health() -> dict:
        try:
            get_predictor()
            loaded = True
        except HTTPException:
            loaded = False
        return {"status": "ok", "model_loaded": loaded}

    @application.get("/config", tags=["meta"])
    def config() -> dict:
        """当前实例生效的配置摘要（脱敏）。

        这是 12-Factor 的可视化证据：同一个镜像在 dev / staging / production
        下运行，这里返回的 app_env 会不同，而镜像本身完全相同。
        注意：只返回"密钥是否已配置"，绝不返回密钥本身。
        """
        return settings.safe_view()

    @application.get("/model-info", response_model=ModelInfo, tags=["meta"])
    def model_info() -> ModelInfo:
        predictor = get_predictor()
        meta = predictor.meta
        return ModelInfo(
            n_features=len(predictor.feature_names),
            classes=predictor.classes,
            feature_names=list(predictor.feature_names),
            mlflow_run_id=str(meta.get("mlflow_run_id", "unknown")),
            data_version=str(meta.get("data_version", "unknown")),
            trained_at=str(meta.get("trained_at", "unknown")),
            categorical_encodings=meta.get("categorical_encodings", {}),
        )

    @application.get("/sample", tags=["predict"])
    def sample() -> dict:
        """全 0 的合法输入：在 /docs 里一点就能试，不用手抄几十个字段。"""
        predictor = get_predictor()
        return {"features": {name: 0.0 for name in predictor.feature_names}}

    @application.post("/predict", response_model=PredictionResponse, tags=["predict"])
    def predict(record: ConnectionInput) -> dict:
        predictor = get_predictor()
        given = set(record.features)
        expected = set(predictor.feature_names)
        missing = [name for name in predictor.feature_names if name not in given]
        unexpected = [name for name in record.features if name not in expected]
        if missing or unexpected:
            detail = [
                {
                    "loc": ["body", "features", name],
                    "msg": "缺少特征",
                    "type": "value_error.missing",
                }
                for name in missing
            ] + [
                {
                    "loc": ["body", "features", name],
                    "msg": "多余特征",
                    "type": "value_error.extra",
                }
                for name in unexpected
            ]
            raise HTTPException(status_code=422, detail=detail)
        return predictor.predict(record.features)

    return application


app = create_app()
