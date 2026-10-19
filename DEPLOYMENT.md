# 部署说明（DEPLOYMENT）

## 1. 分支与流水线

| 分支 | 触发 | 作业 | 是否部署 |
|---|---|---|---|
| `feature/*` | push / pull request | 无（不触发流水线） | 否 |
| PR 到 `dev` | pull_request | `lint-and-test`、`docker-build` | 否（只验证） |
| `dev` | push | `lint-and-test`、`docker-build` | 否 |
| `staging` | push（由 dev 合并而来） | 上述两项 + `build-staging` | 是（staging 环境） |
| `main` | push（由 staging 合并而来） | 上述两项 + `build-prod` | 是（prod 环境，需人工审批） |

## 2. 环境与密钥

| 层级 | 位置 | 用途 |
|---|---|---|
| 仓库级 secrets | Settings → Secrets and variables → Actions | 全局通用配置（兜底） |
| 环境级 secrets | Settings → Environments → `staging` / `prod` | 按环境隔离，优先级高于仓库级 |

- `staging` 环境限定从 `staging` 分支部署；
- `prod` 环境限定从 `main` 分支部署，并配置 Required reviewers，审批通过后才继续。

## 3. 构建与提升

每次合并都会在对应环境重新构建一次镜像：

    PR      -> docker build -t nsl-kdd:ci         （只验证能构建 + 冒烟）
    staging -> docker build -t nsl-kdd:staging    （STAGING_* 密钥 -> .env）
    main    -> docker build -t nsl-kdd:prod       （PROD_*   密钥 -> .env）

**关键点：三次构建出的镜像内容完全相同。** Dockerfile 里没有任何环境专属值，
`APP_ENV` 只是一个标签、不参与任何业务分支；真正的环境差异（密钥、日志级别）
全部由 `.env` 在**运行时**注入：

    docker build ...                 # 与环境无关的构建产物
    docker run --env-file .env ...   # 环境差异只发生在这一层

这满足 12-Factor 的 Build / Release / Run 分离：**换环境 = 换配置，而不是改代码**。
因此同一个镜像 tag 可以在三个环境运行。

## 4. 回滚

1. 在 `main` 上回退到上一个提交，重新走一次提升流程；
2. 直接用上一版镜像标签运行：`docker run nsl-kdd:<旧 commit-sha>`；
3. 模型级回滚目标记录在 `ml/registry/current_model.md`，含 run_id 与 baseline 回滚 run。

## 5. 本地验证与容器

    python ml/train.py --all          产出 models/model.joblib 与 model_meta.json
    docker build -t nsl-kdd:local .
    docker run --rm -p 8000:8000 nsl-kdd:local
    curl http://127.0.0.1:8000/health

## 6. 故障排查

| 现象 | 检查点 |
|---|---|
| 容器起不来 | 看 `docker logs`，确认 `MODEL_PATH` 指向 `models/model.joblib` |
| /health 返回 model_loaded false | 确认 `models/` 没有被 `.dockerignore` 排除 |
| build-staging 作业没出现 | 确认 `ci.yml` 的 `on.push.branches` 含 `staging`，且作业 `if` 条件匹配 |
| prod 部署停在等待 | 环境配了 Required reviewers，需要在 Actions 页面点 Approve |

---

## 7. 配置管理（12-Factor：Factor III Config）

配置 = 在不同部署之间会变的东西（凭据、端点、开关）。本项目把它们全部放在环境变量里。

### 7.1 配置从哪里来、到哪里去

| 场景 | 配置来源 | 注入方式 |
|---|---|---|
| 本地开发 | 仓库根目录的 `.env`（模板 `.env.example`） | uvicorn 读进程环境 / `python-dotenv` |
| CI 的 PR 检查 | 不需要业务配置 | `docker build --build-arg APP_ENV=ci` + 无密钥冒烟 |
| 合并到 staging | GitHub Secrets `STAGING_*` | 先写 `.env`，再 `docker run --env-file .env` |
| 合并到 main | GitHub Secrets `PROD_*` | 同上 |

### 7.2 三条硬规则

1. **`.env` 不进 Git、不进镜像。** 已同时写入 `.gitignore` 与 `.dockerignore`；
   仓库里只有不含真实值的 `.env.example`。
2. **镜像里没有配置值。** `docker history` / `docker save` 都挖不到密钥，
   因为密钥根本没参与构建。
3. **日志里不出现密钥。** CI 打印 `.env` 时用 `sed 's/=.*/=***/'` 遮蔽；
   应用侧 `/health` 只返回 `api_key_configured: true/false`。

### 7.3 代码侧实现

- `app/settings.py`：pydantic `Settings`，用 `Field(alias="APP_ENV")` 把字段绑定到环境变量名，
  带类型校验与默认值。
- `get_settings()`：从 `os.environ` 构造配置对象（`extra="ignore"` 忽略无关变量）。
- `validate_for_env()`：**fail fast** —— `APP_ENV=production` 却没有 `APP_API_KEY` 时直接退出，
  不让"带病"实例上线。
- `safe_view()`：只输出"有没有配"的脱敏摘要，永不返回密钥原文。

配置项一览见 `README.md` 第 5 节。

---

## 8. CI 与分支保护的启用顺序（为什么必须是这个顺序）

GitHub 的 branch protection 里，`Require status checks to pass` 的**下拉列表只有在某个检查
至少运行过一次之后才会填充**。也就是说：**必须先有 CI、先跑出一次运行记录，才能勾选检查名。**

因此本项目的实际启用顺序是：

1. 先上线 `.github/workflows/ci.yml`；
2. 让流水线在 `dev` 上跑出一次成功记录；
3. 再为 `dev` / `staging` / `main` 添加 branch protection，勾选
   `lint-and-test` 与 `docker-build`。

这个顺序带来一个客观结果：**在保护规则添加之前，GitHub 层面并不阻止红灯 PR 合并。**

- 早期某次 PR 曾在 CI 尚未通过时被合并，问题随后由后续提交修复（提交历史可查）。
- 从保护规则添加那一刻起，红灯 PR 在机制上**无法合并** —— Merge 按钮变灰并提示
  `Required status checks have not passed`。

**证据清单（答辩素材）**：

| 证据 | 说明 |
|---|---|
| 红灯 PR 截图 | 红色检查 + 灰色 Merge 按钮 + blocked 提示 |
| `Settings → Branches` 截图 | 三条分支的保护规则 |
| 已合并 PR 截图 | 两个绿色检查（`lint-and-test`、`docker-build`） |
| Actions 页面 | `build-staging` / `build-prod` 的成功记录 |

> 说明：本项目按课程要求只需"自动化构建阶段"，不包含 release / publish 到镜像仓库的流程。
> `build-staging` 与 `build-prod` 的产出是"用该环境配置构建成功并通过 `/health` 冒烟"的镜像。
