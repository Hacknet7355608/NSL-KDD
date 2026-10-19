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

镜像只在第一次构建时生成，标签使用提交短哈希 `<commit-sha>`。
提升到 staging / prod 时复用同一个镜像标签，只切换环境变量：

    build（一次） -> 镜像 nsl-kdd:<commit-sha>
          ├── staging：docker run + STAGING_* 变量
          └── prod   ：docker run + PROD_* 变量（需审批）

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