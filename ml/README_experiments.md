# 实验总结（ml/README_experiments.md）

## 1. 优化指标：为什么是 F1，而不是 accuracy

NSL-KDD 训练集 125,973 行里，normal 占 53.5%（67,343 行），其余四类攻击共 58,630 行，
其中 U2R 只有 52 行、R2L 只有 995 行。

- 若只看 accuracy：把所有流量都判成 normal 也能拿到 53.5%，但 U2R（提权）一条都抓不到；
- 官方测试集 KDDTest+（22,544 行）含训练时未出现的攻击类型，
  模型倾向把 R2L/U2R 判成 normal，accuracy 看着尚可、实际漏报严重。

所以本项目同时看三个数：

| 指标 | 含义 | 为什么用它 |
|---|---|---|
| `accuracy` | 整体正确率 | 与课件、与直观预期对齐 |
| `f1_weighted` | 按类别样本量加权的 F1 | **主指标**：类别不平衡时比 accuracy 稳 |
| `f1_macro` | 每类 F1 的算术平均 | 检查少数类（R2L/U2R）是否被放弃 |

本次 `accuracy=0.7405` 而 `f1_weighted=0.6923`，差距就来自少数类召回偏低——
这正是入侵检测里最需要盯的部分，也说明不能只报 accuracy。

## 2. 两个实验（评测集：KDDTest+ 22,544 行）

| 实验 | 配置 | n_estimators | max_depth | accuracy | f1_weighted | f1_macro | run_id |
|---|---|---|---|---|---|---|---|
| baseline | `ml/configs/baseline.json` | 20 | 5 | 0.7377 | 0.6883 | 0.4646 | `8af1294499bf42af9ce1a873269161f0` |
| improved | `ml/configs/improved.json` | 100 | 10 | **0.7405** | **0.6923** | **0.4707** | `5dd7a856663345e6802159111799199f` |

改进的三处设计：

1. **树更多**（20 → 100）：单棵树对训练数据扰动敏感，多棵树投票后方差更小；
2. **树更深**（5 → 10）：深度 5 学不到“源字节数 + 错误率”这类组合规则，属于欠拟合；
3. **固定 `random_state=42`**：两次重跑结果完全一致（见第 5 节），保证实验可复现。

## 3. 生产模型选谁

**选 improved（100 棵树 / 深度 10）。**

理由：

1. 三项指标一致更高（accuracy +0.28pp、f1_weighted +0.40pp、f1_macro +0.61pp），
   不是靠多判 normal 刷分；
2. 模型仅 1.2MB，进镜像与 Git 都无压力，单条预测毫秒级；
3. 超参与实验课 `MLFlowSetup.ipynb` 的第二组配置一致，复现与解释成本最低。

**为什么提升幅度不大（要能解释）：** 在 KDDTest+ 上，瓶颈是“训练时没见过的攻击类型”
（R2L/U2R 的新变种），而不是模型容量。继续加深加树只会增大模型体积、抬高过拟合风险，
换来不到 1 个百分点——这属于收益递减，故停在 100 棵 / 深度 10。

## 4. 每个 run 记录了什么（对应老师的要求）

| 老师要求 | 参数/产物名 | 位置 |
|---|---|---|
| 代码版本（git SHA） | `git_commit` | Parameters |
| 数据版本（DVC 哈希） | `data_version` | Parameters |
| 超参数 | `n_estimators`、`max_depth`、`n_features`、`random_state`、`eval_set` | Parameters |
| 指标 | `accuracy`、`f1_weighted`、`f1_macro` | Metrics |
| 模型权重 | `model/` | Artifacts |
| 混淆矩阵 | `plots/confusion_matrix.png` | Artifacts |
| 分类报告 | `reports/classification_report.txt` | Artifacts |

## 5. 复现

```powershell
$env:MLFLOW_ALLOW_FILE_STORE = "true"     # MLflow 3.x 默认禁用 file store，必须显式放行
.\.venv\Scripts\python.exe ml\train.py --all
.\.venv\Scripts\mlflow.exe ui --backend-store-uri ./mlruns --port 5000
```

**可复现性验证**：清空 `mlruns/` 后重跑，两项实验的三项指标与 run 记录前完全一致
（0.7377 / 0.7405），因为数据版本固定、`random_state=42` 固定。

**环境备注**（踩过的坑，便于他人复现）：

- MLflow 3.17.1 默认把 sklearn 模型用 `skops` 序列化，树模型必须显式信任节点类型，
  否则 `log_model` 报 `UntrustedTypesFoundException`；
  `ml/train.py` 里已加 `skops_trusted_types=["sklearn.tree._tree.Tree"]`。
- matplotlib 默认字体不含中文，混淆矩阵会显示方框；
  `ml/train.py` 已设置 `font.sans-serif = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']`。
