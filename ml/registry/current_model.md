# 当前生产模型登记表

> 每次换模型都要更新本文件，并在 PR 描述里说明换了什么、为什么换。

| 项 | 值 |
|---|---|
| 登记时间 | 2026-10-19 |
| 模型 | RandomForest 100 棵 / 深度 10（`ml/configs/improved.json`） |
| MLflow run_id | `5dd7a856663345e6802159111799199f` |
| 数据版本 | `data-v2`（DVC md5 `d59de9c1ad2115ceebc67ef153f461cb`） |
| 代码 commit | `59bb4a2` |
| 评测集 | KDDTest+（22,544 行，含未见攻击） |
| accuracy | 0.7405 |
| f1_weighted | 0.6923 |
| f1_macro | 0.4707 |
| 模型大小 | 1.2 MB |
| 上线路径 | `models/model.joblib` → 镜像 `/app/models/model.joblib` |
| 回滚目标 | baseline run `8af1294499bf42af9ce1a873269161f0`（artifacts 里的 `model/`，需用 joblib 重新导出） |

## 变更记录

| 日期 | 变更 | 原因 | 审批人 |
|---|---|---|---|
| 2026-10-19 | 首次登记 improved（100 棵 / 深度 10） | 三项指标均高于 baseline，模型仅 1.2MB | A |
