# NSL-KDD ｜ 网络入侵检测系统

输入一条网络连接的特征（协议类型、字节数、错误率等），输出它属于
`normal` / `DoS` / `Probe` / `R2L` / `U2R` 中的哪一类。

项目把一学期的 DevOps + MLOps 工具串成一条完整链路：

**Git 分支管理 → DVC 数据版本 → MLflow 实验追踪 → FastAPI 服务 → 自动化测试 → Docker 镜像 → GitHub Actions 流水线 → 分环境构建**

> 课程：DevOps 与 MLOps
> 小组：`21`
> 成员：A（数据与训练）、B（服务与测试）、C（容器、配置与流水线）

---

## 目录

1. [项目概览](#1-项目概览)
2. [目录结构](#2-目录结构)
3. [本地开发](#3-本地开发)
4. [配置管理（12-Factor）](#4-配置管理12-factor)
5. [API 端点](#5-api-端点)
6. [从提交到生产（评分重点）](#6-从提交到生产评分重点)
7. [CI 流水线详解](#7-ci-流水线详解)
8. [测试](#8-测试)
9. [代码质量自动化](#9-代码质量自动化)
10. [团队分工](#10-团队分工)
11. [故障排查](#11-故障排查)
12. [更多文档](#12-更多文档)

---

## 1. 项目概览

| 项 | 值 |
|---|---|
| 任务 | NSL-KDD 网络流量**五分类** |
| 模型 | scikit-learn RandomForest（从零训练，两个实验：baseline + improved） |
| 数据版本 | DVC v1（原始）/ v2（合并 5 类标签、编码类别特征、删除常量列），远程存储 Azure Blob |
| 实验追踪 | MLflow 2，本地 `file:./mlruns` 后端 |
| 服务 | FastAPI + Uvicorn，6 个端点 |
| Python | **3.12**（本地 / CI / 镜像三处统一） |
| 测试 | pytest，6 个测试文件共 **36 个用例** |
| 镜像 | `python:3.12-slim`（经 Azure 容器镜像源拉取），非 root 运行，带 `HEALTHCHECK` |
| 流水线 | GitHub Actions，4 个作业 |
| 配置 | 12-Factor：全部走环境变量，密钥不进代码、不进镜像 |

---

## 2. 目录结构

```
NSL-KDD/
├── app/                            # 服务代码
│   ├── __init__.py
│   ├── main.py                     # FastAPI 入口：/ /health /config /model-info /sample /predict
│   ├── model.py                    # 模型加载 + 特征顺序校验（缺失时降级为 503）
│   ├── schemas.py                  # Pydantic 请求/响应模型
│   └── settings.py                 # 配置层：环境变量 -> 类型化 Settings（12-Factor）
│
├── ml/                             # 数据与训练
│   ├── data_pipeline.py            # v1 原始 txt -> v2 清洗编码
│   ├── train.py                    # 训练 + MLflow 记录 + 导出 models/
│   ├── configs/
│   │   ├── baseline.json           # 实验一：小模型
│   │   └── improved.json           # 实验二：更大更深的模型
│   ├── registry/
│   │   └── current_model.md        # 当前生产模型登记表（run_id / 数据版本 / 指标 / 回滚目标）
│   ├── README_data.md              # 数据来源、v1 -> v2 变化、版本与 commit 对应
│   ├── README_experiments.md       # 两个实验对比、生产模型选择理由
│   └── PROVENANCE.md               # 模型血缘：run_id <-> commit <-> 数据版本
│
├── models/                         # 训练产物（提交进 Git，供镜像与 CI 使用）
│   ├── model.joblib
│   └── model_meta.json             # feature_names / classes / run_id / 数据版本 / 指标 / 编码表
│
├── tests/                          # 测试（36 个用例）
│   ├── conftest.py                 # 夹具：现场训练小模型，测试不依赖真实数据集
│   ├── test_service.py             # 服务启动、健康检查、模型元信息
│   ├── test_prediction.py          # 预测接口契约
│   ├── test_validation.py          # 输入校验与边界情况
│   ├── test_model_missing.py       # 模型缺失时的降级行为
│   └── test_settings.py            # 配置层：环境变量、脱敏、fail fast
│
├── data/                           # 数据（Git 里只有 .dvc 指针，没有数据本体）
│   ├── raw.dvc                     # v1
│   └── processed.dvc               # v2
│
├── .github/workflows/ci.yml        # GitHub Actions 流水线
├── .pre-commit-config.yaml         # 提交前本地钩子
├── .env.example                    # 本地配置模板（不含真实密钥，可提交）
├── Dockerfile
├── .dockerignore
├── requirements.txt                # 运行依赖（进镜像）
├── requirements-dev.txt            # 测试 / 检查依赖
├── requirements-ml.txt             # 训练依赖（不进镜像）
├── pyproject.toml                  # ruff / pytest / coverage 配置
├── DEPLOYMENT.md                   # 环境、密钥、构建、回滚、启用顺序
└── README.md
```

---

## 3. 本地开发

### 3.1 依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate

pip install -r requirements-dev.txt      # 服务 + 测试 + 检查
pip install -r requirements-ml.txt       # 只有做训练时才需要
```

> 依赖分三份的原因：`requirements-ml.txt` 里的 pandas / mlflow / dvc[azure] / matplotlib
> 加起来有几百 MB，而运行镜像只需要 `requirements.txt` 里那 6 个包。
> 混在一起镜像会从 ~700MB 涨到 1.2GB 以上，"slim" 就名不副实了。

### 3.2 本地配置

```powershell
Copy-Item .env.example .env      # 复制模板后按需填值
```

`.env` 已在 `.gitignore` 与 `.dockerignore` 中排除，**永远不会进仓库、也不会进镜像**。

### 3.3 取数据（DVC 指针 + Azure 远程）

```powershell
dvc pull
```

### 3.4 预处理与训练

```powershell
python ml/data_pipeline.py                    # v1 -> v2
python ml/train.py --all                      # 跑两个实验，产物写入 models/
mlflow ui --backend-store-uri ./mlruns        # 打开 http://127.0.0.1:5000
```

### 3.5 启动服务

```powershell
uvicorn app.main:app --reload --port 8000     # 交互文档：http://127.0.0.1:8000/docs
```

### 3.6 跑测试与检查

```powershell
pytest -q --cov=app --cov-report=term-missing
ruff check .
ruff format --check .
```

### 3.7 启用提交前钩子（每个开发者做一次）

```powershell
pre-commit install
pre-commit run --all-files
```

### 3.8 构建并运行镜像

```powershell
docker build --build-arg APP_ENV=dev -t nsl-kdd:dev .
docker run -d --name nids -p 8000:8000 nsl-kdd:dev
curl http://127.0.0.1:8000/health
docker exec nids ls /app/models          # model.joblib / model_meta.json
docker exec nids ls /app/data            # 应报 No such file（数据不进镜像）
```

---

## 4. 配置管理（12-Factor）

遵循 **12-Factor App — Factor III: Config**：配置与代码分离，同一份构建产物可在多个环境运行。

### 4.1 配置项

| 环境变量 | 默认值 | 是否敏感 | 说明 |
|---|---|---|---|
| `APP_ENV` | `dev` | 否 | 环境标识（dev / staging / production），**不参与任何业务分支** |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别 |
| `MODEL_PATH` | `models/model.joblib` | 否 | 模型文件路径 |
| `MODEL_META_PATH` | `models/model_meta.json` | 否 | 模型元数据路径 |
| `APP_API_KEY` | 空 | **是** | 接口密钥；生产环境必填 |

### 4.2 配置从哪里来

| 场景 | 配置来源 | 注入方式 |
|---|---|---|
| 本地开发 | 仓库根目录 `.env`（模板 `.env.example`） | uvicorn 读进程环境 / `python-dotenv` |
| CI 的 PR 检查 | 不需要业务配置 | `docker build --build-arg APP_ENV=ci`，无密钥冒烟 |
| 合并到 `staging` | GitHub Secrets `STAGING_*` | 先写 `.env`，再 `docker run --env-file .env` |
| 合并到 `main` | GitHub Secrets `PROD_*` | 同上 |

### 4.3 三条硬规则

1. **`.env` 不进 Git、不进镜像** —— 仓库里只有不含真实值的 `.env.example`。
2. **镜像里没有任何配置值** —— 密钥不参与构建，`docker history` / `docker save` 都挖不到。
3. **日志里不出现密钥** —— CI 打印 `.env` 用 `sed 's/=.*/=***/'` 遮蔽；
   应用侧 `GET /config` 只返回 `api_key_configured: true/false`，永不返回原值。

### 4.4 代码侧实现

| 位置 | 作用 |
|---|---|
| `app/settings.py` → `Settings(BaseModel)` | 用 `Field(alias="APP_ENV")` 把字段绑定到环境变量，带类型校验与默认值 |
| `get_settings()` | 从 `os.environ` 构造配置对象（`extra="ignore"` 忽略无关变量） |
| `validate_for_env()` | **fail fast**：`APP_ENV=production` 却缺 `APP_API_KEY` 时直接退出 |
| `safe_view()` | 输出脱敏摘要，供 `GET /config` 使用 |

> 同一个镜像在 `staging` 与 `production` 下运行，`GET /config` 返回的 `app_env` 不同，
> 而镜像是同一个——这就是 Build / Release / Run 分离的直接证据。

---

## 5. API 端点

| 方法 | 路径 | 说明 | 备注 |
|---|---|---|---|
| GET | `/` | 服务基本信息 | 含版本与文档入口 |
| GET | `/health` | 健康检查 | 恒返回 200；`{"status":"ok","model_loaded":bool}` |
| GET | `/config` | 当前生效配置（脱敏） | `app_env` / `log_level` / `model_path` / `api_key_configured` |
| GET | `/model-info` | 模型元信息 | 特征数、类别、run_id、数据版本、编码表 |
| GET | `/sample` | 一份全 0 的合法输入 | 方便在 `/docs` 里一键试调 |
| POST | `/predict` | 五分类预测 | 返回预测类别、置信度、五类概率 |

**降级设计**：模型缺失时 `/health` 仍返回 200（`model_loaded=false`），
`/predict` 返回 503 并说明原因——容器不会因为缺模型而起不来。

---

## 6. 从提交到生产（评分重点）

### 6.1 代码怎么流动

```
① 本地开发                          ② 远端                              ③ 自动化（GitHub Actions）
-----------                         -----                              -----------------------
git commit ─────────────────────►   feature/xxx
（pre-commit 先跑 ruff）
                                          │
                                          │ PR
                                          ▼
                                       dev        ──►  lint-and-test（ruff check + format + pytest）
                                          │                    │
                                          │                    ▼
                                          │            docker-build（构建 + /health 冒烟）
                                          │                    │
                                          │        ✓ 两个检查都绿才允许合并（分支保护）
                                          │
                                          │ PR
                                          ▼
                                     staging      ──►  lint-and-test
                                          │                    │
                                          │                    ▼
                                          │            build-staging
                                          │            （STAGING_* → .env → 构建 nsl-kdd:staging）
                                          │
                                          │ PR
                                          ▼
                                       main       ──►  lint-and-test
                                                           │
                                                           ▼
                                                    build-prod
                                                    （PROD_* → .env → 构建 nsl-kdd:prod）
```

**一句话概括**：
`commit →（pre-commit + ruff）→ push → PR 到 dev → 全量测试 + 静态检查 + 构建镜像 → 合并到 dev → PR 到 staging → 构建 staging 镜像 → PR 到 main → 构建生产镜像`。

### 6.2 哪个分支触发哪条流水线

| 分支 / 事件 | 触发哪些作业 |
|---|---|
| push 到 `feature/*` | **不触发**（只在发起 PR 时被检查） |
| PR 到 `dev` / `staging` / `main` | `lint-and-test` → `docker-build` |
| push 到 `dev`（即合并 PR） | `lint-and-test` → `docker-build` |
| push 到 `staging`（即合并 PR） | `lint-and-test` → `docker-build` → **`build-staging`** |
| push 到 `main`（即合并 PR） | `lint-and-test` → `docker-build` → **`build-prod`** |
| 手动 `Run workflow` | `lint-and-test` → `docker-build`（两个环境构建作业按 `if` 条件跳过） |

> `build-staging` / `build-prod` **只在合并（push）时运行**，这是设计如此：
> 课程要求的是 "**Merges to** staging/main → 生成 .env → 构建对应环境镜像"。
> 在 PR 视图里它们显示为 skipped 是正常的。

### 6.3 三个环境的对应关系

| GitHub Environment | 分支 | `APP_ENV` | 镜像 tag | 备注 |
|---|---|---|---|---|
| （无） | `dev` | `ci` | `nsl-kdd:ci` | 只验证能构建 + 冒烟 |
| `staging` | `staging` | `staging` | `nsl-kdd:staging` | 使用环境级 `STAGING_*` 密钥 |
| `prod` | `main` | `production` | `nsl-kdd:prod` | 使用环境级 `PROD_*` 密钥，**需人工审批** |

### 6.4 保护规则

`dev`、`staging`、`main` 三条长期分支均已启用 branch protection：

- 必须通过 PR 才能合入，**不允许直接 push**
- 必须通过 `lint-and-test` 与 `docker-build` 两个状态检查
- 不允许绕过（`Do not allow bypassing the above settings`）

即：**CI 失败时 PR 无法合并**，Merge 按钮会变为灰色并提示
`Required status checks have not passed`。

更详细的启用顺序与证据清单见 `DEPLOYMENT.md` 第 7、8 节。

---

## 7. CI 流水线详解

配置文件：`.github/workflows/ci.yml`

| 作业 | 触发条件 | 做什么 | 失败会怎样 |
|---|---|---|---|
| `lint-and-test` | 所有 PR / push 到三条分支 | `pip install -r requirements-dev.txt` → `ruff check .` → `ruff format --check .` → `pytest -q --cov=app` | 后续作业不再执行，PR 无法合并 |
| `docker-build` | 同上，`needs: lint-and-test` | `docker build` + 启动容器请求 `/health` 做冒烟 | PR 无法合并 |
| `build-staging` | `push` 到 `staging` | 写 `.env` → 构建 `nsl-kdd:staging` → `--env-file` 启动并验证 `/health` | 该分支的流水线红 |
| `build-prod` | `push` 到 `main` | 写 `.env` → 构建 `nsl-kdd:prod` → `--env-file` 启动并验证 `/health` | 该分支的流水线红；配了审批则会先停在 Waiting |

两个细节：

- **冒烟测试是"真"的**：用显式 `exit 1` 判定，而不是靠 `for` 循环自然结束——
  否则 20 次全失败也会被判为成功，变成一条假防线。
- **`.env` 有真实消费者**：它不是构建输入，而是运行时配置，通过 `docker run --env-file` 注入。
  构建与配置分离，同一个镜像可以跑三个环境。

---

## 8. 测试

| 文件 | 覆盖的功能点 | 边界情况 |
|---|---|---|
| `tests/test_service.py` | 服务启动、健康检查、模型元信息 | 未知路由 404、元信息字段完整性 |
| `tests/test_prediction.py` | 预测接口契约 | 全 0、负数、1e6、小数、幂等性、`/sample` 直接提交 |
| `tests/test_validation.py` | 输入校验 | 缺字段、多字段、字符串/null/list 类型、空对象、缺 body、方法错、非 JSON |
| `tests/test_model_missing.py` | 模型缺失降级 | 无模型 503、meta 损坏、`/health` 仍 200 |
| `tests/test_settings.py` | 配置层 | 环境变量读取、默认值回落、密钥不外泄、生产缺密钥 fail fast、`/health` 契约不被破坏 |

共 **36 个用例**。测试夹具（`conftest.py`）现场训练一个极小模型，
**不依赖真实数据集**，因此在 CI 里无需 `dvc pull` 也能跑。

```powershell
pytest -q --cov=app --cov-report=term-missing
```

---

## 9. 代码质量自动化

两道关卡，规则完全一致：

| 关卡 | 位置 | 跑什么 |
|---|---|---|
| 提交前（本地） | `.pre-commit-config.yaml` | `ruff --fix`、`ruff-format`、文件末尾换行、行尾空格、YAML 语法、大文件、合并冲突标记 |
| PR 时（CI） | `ci.yml` → `lint-and-test` | `ruff check .`、`ruff format --check .`、`pytest` |

```powershell
pre-commit install          # 激活钩子
pre-commit run --all-files  # 手动全量检查
```

规则配置在 `pyproject.toml`：

- `line-length = 100`
- `select = ["E", "F", "I"]`（E/F 等价 flake8，I 等价 isort）
- `ignore = ["E501"]`
- `pythonpath = ["."]` —— 解决 CI 里 `ModuleNotFoundError: app`

`pytest` 与 `ruff` 在 `requirements-dev.txt` 里**版本 pin 死**，保证"本地绿 = CI 绿"。

---

## 10. 团队分工

| 成员 | 负责 | 主要产出 |
|---|---|---|
| **A** | 数据与训练 | `ml/data_pipeline.py`、`ml/train.py`、`ml/configs/`、`data/*.dvc`、`models/*`、`ml/README_data.md`、`ml/README_experiments.md`、`ml/PROVENANCE.md`、`ml/registry/current_model.md` |
| **B** | 服务与测试 | `app/main.py`、`app/model.py`、`app/schemas.py`、`tests/*`（除 `test_settings.py`） |
| **C** | 容器、配置与流水线 | `Dockerfile`、`.dockerignore`、`.github/workflows/ci.yml`、`app/settings.py`、`.env.example`、`.pre-commit-config.yaml`、`requirements*.txt`、`pyproject.toml`、`README.md`、`DEPLOYMENT.md`、分支保护与环境配置 |

---

## 11. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `ruff format --check` 红 | 代码没格式化 | `ruff format .` 后重推（本地 `pre-commit` 可提前拦住） |
| CI 报 `ModuleNotFoundError: app` | 缺 `pythonpath` | `pyproject.toml` 里 `pythonpath = ["."]` |
| `docker build` 报 `COPY failed: models not found` | `models/` 没进 Git | 确认 `models/model.joblib` 已提交 |
| 容器 healthy 但 `/predict` 503 | 镜像里没有模型 | 检查 `Dockerfile` 的 `COPY models` 与 `.dockerignore` 是否误排除 |
| `build-staging` / `build-prod` 显示 skipped | 当前是 PR 事件 | 正常；合并（push）到对应分支才会运行 |
| `build-prod` 停在 Waiting | `prod` 环境配了 Required reviewers | 去 Actions 页面点 `Approve deployment` |
| 镜像拉不到基础镜像 | 网络无法访问 Docker Hub | 本项目通过 Azure 镜像源拉取；若也不可达，换回 `python:3.12-slim` 并为 Docker 配置 registry mirror |
| `/config` 显示 `api_key_configured: false` | 该环境没注入 `APP_API_KEY` | 检查 secrets 与环境级密钥是否已配置 |

---

## 12. 更多文档

| 文档 | 内容 |
|---|---|
| `ml/README_data.md` | 数据来源、v1 → v2 的变化、数据版本与 commit 的对应关系 |
| `ml/README_experiments.md` | 两个 MLflow 实验的对比、生产模型的选择理由、优化指标说明 |
| `ml/PROVENANCE.md` | 模型血缘：`run_id` ↔ `code commit` ↔ `data version` ↔ 模型文件 |
| `ml/registry/current_model.md` | 当前生产模型登记表与回滚目标 |
| `DEPLOYMENT.md` | 环境与分支对应、四个作业、密钥配置、构建与回滚、CI 与分支保护的启用顺序 |
