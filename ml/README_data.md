# 数据说明（ml/README_data.md）

## 1. 数据来源

| 项 | 内容 |
|---|---|
| 数据集 | NSL-KDD（KDD'99 的去冗余改进版） |
| 下载地址 | https://github.com/jmnwong/NSL-KDD-Dataset |
| 说明 | UNB 官方站点已停止提供下载，使用该公开镜像；备用镜像 https://github.com/defcom17/NSL_KDD |
| 原始文件 | `data/raw/KDDTrain+.txt`（125,973 行）、`data/raw/KDDTest+.txt`（22,544 行） |
| 文件格式 | 无表头 CSV，43 列 = 41 个特征 + `label` + `difficulty` |
| 许可证 | 允许再分发与镜像，使用时须引用原文 |
| 引用 | Tavallaee, Bagheri, Lu, Ghorbani, "A Detailed Analysis of the KDD CUP 99 Data Set", CISDA 2009 |

## 2. v1 → v2 改了什么

| 版本 | 内容 | Git tag |
|---|---|---|
| v1 | 官方原始 txt，字节未改动（2 个文件，22,550,937 字节） | `data-v1` |
| v2 | 5 类标签合并 + 类别特征整数编码 + 删除全常量列（6 个文件，26,498,216 字节） | `data-v2` |

v2 做了三处处理：

1. **标签合并**：原始 22 种训练攻击名合并为 5 大类（normal / DoS / Probe / R2L / U2R），
   映射表在 `ml/data_pipeline.py` 的 `ATTACK_MAP` 里，覆盖 KDDTest+ 额外出现的 17 种攻击；
   遇到未映射的攻击名直接报错，不静默丢弃样本。
2. **类别特征编码**：`protocol_type` / `service` / `flag` 编码为整数。
   采用“排序后的固定映射表”而不是 `LabelEncoder`，映射写入 `encoders.json`
   并随模型导出到 `model_meta.json`，API 端复用同一份映射。
   评估集中训练集未出现过的 `service` 取值统一编码为 `-1`。
3. **删除全常量列**：`num_outbound_cmds` 在整份数据中恒为 0，对分类无信息量。
   实际删除的列记录在 `data/processed/dataset_stats.json` 的 `dropped_constant_columns`。
   因此 v2 最终是 **40 个特征**（41 − 1）。

## 3. 版本 ↔ commit ↔ DVC 哈希 对照表

| 版本 | Git tag | 对应 commit | DVC 指针文件 | DVC 内容哈希（md5） | 大小 | 行数 / 特征数 |
|---|---|---|---|---|---|---|
| v1 | data-v1 | `a43470e` | `data/raw.dvc` | `aa8d4e08bd5fc3f3149346fdbe21de0c` | 22,550,937 B（2 文件） | 125,973 + 22,544 行 / 41 特征 |
| v2 | data-v2 | `59bb4a2` | `data/processed.dvc` | `d59de9c1ad2115ceebc67ef153f461cb` | 26,498,216 B（6 文件） | 125,973 + 22,544 行 / 40 特征 |

v2 的 DVC 哈希会被 `ml/train.py` 自动写进每次 MLflow run 的 `data_version` 参数，
因此可以反向回答“这个模型是用哪版数据训练的”。

## 4. 复现

```powershell
git checkout data-v2
dvc pull
python ml/data_pipeline.py --raw data/raw/KDDTrain+.txt --out data/processed --test-raw data/raw/KDDTest+.txt
python ml/train.py --all
```

切回 v1：

```powershell
git checkout data-v1
dvc pull
```

## 5. 什么进了 Git，什么没进

| 内容 | 位置 | 说明 |
|---|---|---|
| 19MB 原始 txt | Azure Blob 容器 `wut2026/dvc` | 只通过 `dvc push/pull` 传输 |
| `.dvc` 指针（几百字节） | Git | 记录内容哈希，不含数据本体 |
| `encoders.json`、`dataset_stats.json` | 随 v2 被 DVC 跟踪 | 保证编码一致、可追溯 |
| SAS token | `.dvc/config.local` | 本地文件，被 DVC 默认忽略，未提交 |
