# 模型血缘（PROVENANCE）

> 一句话：任何一个上线的 `model.joblib`，都能沿着这张表倒推回
> “哪次实验、哪段代码、哪版数据”。

## 1. 当前生产模型

| 项 | 值 |
|---|---|
| 模型文件 | `models/model.joblib`（1.2MB） |
| 元数据 | `models/model_meta.json` |
| 实验名 / run_id | `nsl-kdd` / `5dd7a856663345e6802159111799199f` |
| 配置 | `ml/configs/improved.json`（RandomForest，100 棵 / 深度 10） |
| 训练代码 commit | `59bb4a2`（`data(v2)` 提交之后的 HEAD） |
| 数据版本 | tag `data-v2`，DVC md5 `d59de9c1ad2115ceebc67ef153f461cb` |
| 评测集 | KDDTest+（22,544 行，含未见攻击） |
| 指标 | accuracy 0.7405 / f1_weighted 0.6923 / f1_macro 0.4707 |
| 特征数 | 40（41 − 删除的常量列 `num_outbound_cmds`） |
| 训练时间 | 2026-10-19（UTC，精确到秒见 `models/model_meta.json`） |

## 2. 全部实验记录

| run_id | 实验 | 代码 commit | 数据版本（md5） | f1_weighted | 产出 |
|---|---|---|---|---|---|
| `8af1294499bf42af9ce1a873269161f0` | baseline（20 棵 / 深度 5） | `59bb4a2` | `d59de9c1ad2115ceebc67ef153f461cb` | 0.6883 | 仅 MLflow artifacts |
| `5dd7a856663345e6802159111799199f` | improved（100 棵 / 深度 10） | `59bb4a2` | `d59de9c1ad2115ceebc67ef153f461cb` | 0.6923 | 已导出为 `models/` |

## 3. 怎么验证这条链没断

```powershell
# 1) 模型文件里记的 run_id
Select-String -Path models\model_meta.json -Pattern "mlflow_run_id"

# 2) 该 run 记录的数据版本
Select-String -Path mlruns\*\*\params\data_version -Pattern "."

# 3) 当前 .dvc 指针是否仍指向同一版数据
git show data-v2:data/processed.dvc

# 4) 代码是否就是那个 commit
git log --oneline -1 59bb4a2
```

四处对得上，说明“模型 ↔ 数据 ↔ 代码”三者一致；任何一处不一致，都说明
有人绕过了 DVC 或手工改过模型文件。

## 4. 模型元数据里有什么（API 契约来源）

`models/model_meta.json` 的字段与用途：

| 字段 | 用途 |
|---|---|
| `feature_names` | 40 个特征的名字与顺序；API 按它组织输入、校验字段是否齐全 |
| `classes` | 5 个类别名，顺序与 `model.classes_` 一致 |
| `mlflow_run_id` | 回到实验记录 |
| `data_version` | 回到数据版本（DVC md5） |
| `git_commit` | 回到代码版本 |
| `categorical_encodings` | `protocol_type` / `service` / `flag` 的字符串→整数映射 |
| `metrics` | 该模型的评测结果 |
