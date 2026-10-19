"""应用配置：全部来自环境变量（12-Factor App — Factor III: Config）。

设计要点（对应课件 5.1-12 Factor Config）：
  - 配置 = 在不同部署（dev/staging/prod）之间会变的东西：凭据、端点、开关。
  - 配置存在环境变量里，不存在代码里；镜像里不含任何环境专属值。
  - 因此同一份镜像可以在三个环境运行，差异全部由运行时环境变量注入
    （CI 用 `docker run --env-file`，本地开发用 `.env`）。
  - 用 pydantic 做类型校验：缺值/类型错会在启动阶段就报出来，
    而不是等到第一次请求才 500。
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL_PATH = "models/model.joblib"
DEFAULT_META_PATH = "models/model_meta.json"


class Settings(BaseModel):
    """类型化的配置对象。字段名与对应的环境变量名通过 alias 绑定。"""

    model_config = ConfigDict(extra="ignore")

    # 环境标识：目前只用于展示与校验，不参与任何业务分支
    # （12-Factor: "No env-specific branches in the code"）
    app_env: str = Field("dev", alias="APP_ENV")

    # 非敏感配置：给默认值，缺了不影响启动
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    model_path: str = Field(DEFAULT_MODEL_PATH, alias="MODEL_PATH")
    model_meta_path: str = Field(DEFAULT_META_PATH, alias="MODEL_META_PATH")

    # 敏感配置：默认 None，读取后也绝不对外返回原值
    app_api_key: str | None = Field(None, alias="APP_API_KEY")

    @property
    def api_key_configured(self) -> bool:
        """只表达"有没有配"，不暴露取值。"""
        return bool(self.app_api_key)

    def safe_view(self) -> dict[str, object]:
        """可安全返回给 /health 或打进日志的配置摘要（脱敏）。"""
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "model_path": self.model_path,
            "api_key_configured": self.api_key_configured,
        }


def get_settings() -> Settings:
    """从进程环境读取配置。

    pydantic 的 extra="ignore" 会忽略 os.environ 里无关的键，
    所以可以直接把整个环境展开进去。
    """
    return Settings(**dict(os.environ))


def validate_for_env(settings: Settings) -> None:
    """fail fast：生产环境缺密钥就直接退出，不让"带病"的实例上线。

    注意：只在 APP_ENV=production 时强制要求 APP_API_KEY，
    dev / staging 允许为空，否则本地开发和 CI 冒烟都会被挡。
    """
    if settings.app_env == "production" and not settings.app_api_key:
        raise SystemExit(
            "配置缺失：APP_ENV=production 时必须提供 APP_API_KEY"
            "（应由 GitHub Secrets -> .env -> docker run --env-file 注入）"
        )
