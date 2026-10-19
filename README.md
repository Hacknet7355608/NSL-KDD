# NSL-KDD ｜ 网络入侵检测系统

基于 NSL-KDD 数据集的网络流量五分类系统：输入一条网络连接的特征，判断它是
`normal` / `DoS` / `Probe` / `R2L` / `U2R` 中的哪一类。

项目完整走一遍 DevOps + MLOps 流程：
**Git 分支管理 → DVC 数据版本 → MLflow 实验追踪 → FastAPI 服务 → Docker 镜像 → GitHub Actions 流水线**。

> 课程：DevOps 与 MLOps ｜ 小组：`<组号>` ｜ 成员：A（数据/训练）、B（服务/测试）、C（容器与流水线）

---

## 1. 技术栈

| 层次 | 技术 | 作用 |
|---|---|---|
| 数据版本 | DVC 3 + Azure Blob | 原始数据与处理后数据各存一个版本，Git 里只有 `.dvc` 指针 |
| 实验追踪 | MLflow 2（本地 file backend） | 记录超参、指标、混淆矩阵、模型文件与数据版本 |
| 模型 | scikit-learn RandomForest | 多分类，输出 5 类概率 |
| 服务 | FastAPI + Uvicorn | `/`、`/health`、`/config`、`/model-info`、`/sample`、`/predict` |
| 配置 | pydantic Settings + 环境变量 | 12-Factor Config：配置与代码分离，环境差异全部运行时注入 |
| 测试 | pytest + pytest-cov | 6 个测试文件共 36 个用例 |
| 代码质量 | ruff + pre-commit | 本地钩子与 CI 用同一套规则，版本 pin 住 |
| 打包 | Docker（`python:3.12-slim`） | 运行镜像只装依赖，不含数据与训练脚本 |
| 流水线 | GitHub Actions | PR 必过 lint + test + docker build；合并 staging/main 构建对应环境镜像 |

---

## 2. 目录结构

```
NSL-KDD/
├── app/                        # 服务代码
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口：/ /health /config /model-info /sample /predict
│   ├── model.py                # 模型加载 + 特征顺序校验
│   ├── schemas.py              # Pydantic 请求/响应模型
│   └── settings.py             # ★ 配置层：环境变量 -> 类型化 Settings
├── ml/                         # 数据与训练
│   ├── data_pipeline.py        # v1 原始 txt -> v2 清洗编码
│   ├── train.py                # 训练 + MLflow 记录 + 导出 models/
│   ├── configs/                # baseline.json / improved.json
│   ├── registry/current_model.md   # 当前生产模型登记表
│   ├── README_data.md          # 数据来源、v1 -> v2 变化、版本与 commit 对应
│   ├── README_experiments.md   # 两次实验对比、生产模型选择理由
│   └── PROVENANCE.md           # 模型血缘（run_id <-> commit <-> 数据版本）
├── models/                     # 训练产物（提交到 Git，供镜像与 CI 使用）
│   ├── model.joblib
│   └── model_meta.json
├── tests/                      # 测试（36 个用例）
│   ├── conftest.py
│   ├── test_service.py
│   ├── test_prediction.py
│   ├── test_validation.py
│   ├── test_model_missing.py
│   └── test_settings.py        # ★ 配置层测试（monkeypatch）
├── data/                       # 数据（只提交 .dvc 指针，不提交数据本体）
│   ├── raw.dvc
│   └── processed.dvc
├── .github/workflows/ci.yml    # 流水线
├── .pre-commit-config.yaml     # ★ 提交前本地钩子
├── .env.example                # ★ 本地配置模板（不含真实密钥）
├── Dockerfile
├── .dockerignore
├── requirements.txt            # 运行依赖（进镜像）
├── requirements-dev.txt        # 测试/检查依赖
├── requirements-ml.txt         # 训练依赖（不进镜像）
├── pyproject.toml              # ruff / pytest / coverage 配置
├── DEPLOYMENT.md               # 环境、密钥、构建与回滚
└── README.md
```

---

## 3. 本地跑起来

### 1) 依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate                  # macOS/Linux: source .venv/bin/activate
pip install -r requirements-ml.txt        # 训练用
pip install -r requirements-dev.txt       # 服务/测试/检查用
```

> 本项目统一使用 **Python 3.12**（本地、CI、Docker 镜像三处一致，避免版本漂移）。

### 2) 本地配置

```powershell
Copy-Item .env.example .env      # 复制模板后按需填值
```

`.env` 已被 `.gitignore` 与 `.dockerignore` 排除，**永远不会进仓库、也不会进镜像**。

### 3) 取数据（DVC 指针 + Azure 远程）

```powershell
dvc pull
```

### 4) 预处理 + 训练

```powershell
python ml/data_pipeline.py
python ml/train.py --all
mlflow ui --backend-store-uri ./mlruns      # http://127.0.0.1:5000
```

### 5) 起服务

```powershell
uvicorn app.main:app --reload --port 8000   # 文档：http://127.0.0.1:8000/docs
```

### 6) 跑测试与检查

```powershell
pytest -q --cov=app --cov-report=term-missing
ruff check .
ruff format --check .

# 一次性安装提交前钩子（每个开发者做一次）
pre-commit install
pre-commit run --all-files
```

### 7) 构建镜像

```powershell
docker build --build-arg APP_ENV=dev -t nsl-kdd:dev .
docker run -d --name nids -p 8000:8000 nsl-kdd:dev
curl http://127.0.0.1:8000/health
```

---

## 4. 从提交到生产：代码怎么流动

```
本地开发                远端                          自动化（GitHub Actions）
--------                ----                          ----------------------
git commit ──push──►  feature/xxx
（pre-commit 先跑一遍）
                            │
                            │ PR
                            ▼
                          dev          ──►  lint-and-test（ruff check + format + pytest）
                            │                     │
                            │                     ▼
                            │              docker-build（构建 + /health 冒烟）
                            │                     │
                            │        ✓ 通过才允许合并（分支保护）
                            │
                            │ PR
                            ▼
                        staging        ──►  lint-and-test
                            │                     │
                            │                     ▼
                            │              build-staging
                            │              （STAGING_* 密钥 → .env → 构建 nsl-kdd:staging）
                            │
                            │ PR
                            ▼
                          main         ──►  lint-and-test
                                                  │
                                                  ▼
                                           build-prod
                                           （PROD_* 密钥 → .env → 构建 nsl-kdd:prod）
```

### 分支触发表

| 分支 | 角色 | 触发哪条流水线 |
|---|---|---|
| `feature/*` | 个人开发分支 | 不触发（只在发起 PR 时被检查） |
| `dev` | 集成分支，日常合入 | PR 与 push：`lint-and-test` → `docker-build` |
| `staging` | 预发布环境 | PR 与 push：同上；push 时额外 `build-staging` |
| `main` | 生产 | PR 与 push：同上；push 时额外 `build-prod` |

### 保护规则

`dev`、`staging`、`main` 三条长期分支均已启用 branch protection：

- 必须通过 PR 才能合入，**不允许直接 push**
- 必须通过 `lint-and-test` 与 `docker-build` 两个状态检查
- 不允许绕过（`Do not allow bypassing the above settings`）

> 即：**CI 失败时 PR 无法合并**，Merge 按钮会变为灰色。
> 相关的启用顺序与证据见 `DEPLOYMENT.md` 第 8 节。

---

## 5. 配置管理（12-Factor App）

遵循 **12-Factor App Factor III: Config**：

| 原则 | 本项目的做法 |
|---|---|
| 配置存在环境里，不存在代码里 | 全部配置由 `app/settings.py`（pydantic `Settings`）从 `os.environ` 读取 |
| 同一份构建产物跨环境 | 镜像里只有 `APP_ENV` 这个环境标识，不含任何密钥；同一镜像可在 dev/staging/prod 运行 |
| 无环境专属分支 | `APP_ENV` 只用于展示与校验，**不参与任何业务 if/else** |
| 运行时注入 | CI 用 `docker run --env-file .env`；本地用 `.env` |
| 不提交密钥 | `.env` 被 `.gitignore` / `.dockerignore` 排除；仓库里只有 `.env.example` |
| fail fast | `APP_ENV=production` 且缺 `APP_API_KEY` 时启动直接退出 |
| 日志不泄漏密钥 | `GET /config` 只返回 `api_key_configured: true/false`，永不返回原值 |

配置项一览：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `dev` | 环境标识（dev / staging / production） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `APP_API_KEY` | 空 | 接口密钥；生产环境必填 |
| `MODEL_PATH` | `models/model.joblib` | 模型文件路径 |
| `MODEL_META_PATH` | `models/model_meta.json` | 模型元数据路径 |

---

## 6. 关键设计说明

- **模型与代码分离**：训练产物是 `models/model.joblib` + `models/model_meta.json`。服务启动时按
  `model_meta.json` 里的 `feature_names` 顺序组织输入——顺序错了精度会降但不会报错，
  所以顺序由**文件**而不是代码保证。
- **服务可降级**：模型缺失时 `/health` 仍返回 200（`model_loaded=false`），`/predict` 返回 503。
  容器不会因为缺模型而起不来。
- **训练依赖不进镜像**：`requirements-ml.txt` 里的 pandas / mlflow / dvc / matplotlib 只在训练机安装。
- **数据不进 Git**：`data/` 由 DVC 指向 Azure 容器，Git 里只有 `.dvc` 指针。
- **环境配置与构建分离**：环境密钥生成 `.env` 后作为运行时配置注入，不烧进镜像层。

---

## 7. 测试

| 文件 | 覆盖的功能点 | 边界情况 |
|---|---|---|
| `tests/test_service.py` | 服务启动、健康检查、模型元信息 | 未知路由 404、元信息字段完整性 |
| `tests/test_prediction.py` | 预测接口契约 | 全 0、负数、1e6、小数、幂等性、`/sample` 直接提交 |
| `tests/test_validation.py` | 输入校验 | 缺字段、多字段、字符串/null/list 类型、空对象、缺 body、方法错、非 JSON |
| `tests/test_model_missing.py` | 模型缺失降级 | 无模型 503、meta 损坏、`/health` 仍 200 |
| `tests/test_settings.py` | 配置层 | 环境变量读取、默认值回落、`/config` 不泄漏密钥、生产缺密钥 fail fast、`/health` 契约不被破坏 |

当前共 **36 个用例**，覆盖率见 CI 的 `pytest --cov=app` 报告。

---

## 8. 团队分工

| 成员 | 负责 | 主要产出 |
|---|---|---|
| A | 数据与训练 | `ml/data_pipeline.py`、`ml/train.py`、`data/*.dvc`、`models/*`、`ml/README_*.md`、`ml/PROVENANCE.md` |
| B | 服务与测试 | `app/main.py`、`app/model.py`、`app/schemas.py`、`tests/*` |
| C | 容器、配置与流水线 | `Dockerfile`、`.dockerignore`、`.github/workflows/ci.yml`、`app/settings.py`、`.env.example`、`.pre-commit-config.yaml`、`README.md`、`DEPLOYMENT.md`、分支保护 |

---

## 9. 更多文档

- 数据集与版本：`ml/README_data.md`
- 实验记录与选型：`ml/README_experiments.md`
- 模型血缘：`ml/PROVENANCE.md`
- 当前生产模型：`ml/registry/current_model.md`
- 部署与密钥：`DEPLOYMENT.md`
