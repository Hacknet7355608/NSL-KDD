"""训练 + MLflow 记录。

结构照搬 MLflow 实验课里的 train_and_log_model()：
训练 -> 评估 -> log_param / log_metric / log_model，只是多记了
“代码版本（git commit）”和“数据版本（DVC 哈希）”，因为老师要求能倒推。

用法（在仓库根目录执行）：
    python ml/train.py --all                                  # 跑 baseline + improved
    python ml/train.py --config ml/configs/improved.json       # 只跑一个
    mlflow ui --backend-store-uri ./mlruns                     # 打开实验面板
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
EXPERIMENT = "nsl-kdd"


def git_commit() -> str:
    """当前代码版本。老师要求每个 run 都能对上是哪段代码训出来的。"""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def data_version() -> str:
    """从 data/processed.dvc 里取 DVC 的内容哈希，作为“数据版本 ID”。"""
    dvc_file = ROOT / "data" / "processed.dvc"
    if not dvc_file.exists():
        return "unknown"
    found = re.search(r"md5:\s*([0-9a-f]{32})", dvc_file.read_text(encoding="utf-8"))
    return found.group(1) if found else "unknown"


def load_data():
    """有官方 KDDTest+ 就用它评估，否则退化为同分布 8:2 划分。

    注意区别：同分布划分能刷到 0.99，官方测试集（含训练时没见过的攻击）只有 0.78 左右。
    """
    X = pd.read_csv(PROCESSED / "X.csv")
    y = pd.read_csv(PROCESSED / "y.csv")["label"].astype(str)

    if (PROCESSED / "X_test.csv").exists():
        X_test = pd.read_csv(PROCESSED / "X_test.csv")[list(X.columns)]
        y_test = pd.read_csv(PROCESSED / "y_test.csv")["label"].astype(str)
        return X, y, X_test, y_test, "kddtest+"

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    return X_train, y_train, X_test, y_test, "holdout"


def save_confusion_matrix(y_true, y_pred, classes, path: Path) -> bool:
    """混淆矩阵图。没装 matplotlib 就跳过，不影响训练。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    except ImportError:
        return False

    from sklearn.metrics import confusion_matrix

    matrix = confusion_matrix(y_true, y_pred, labels=classes)
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(classes)), classes, rotation=30, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("预测类别")
    ax.set_ylabel("真实类别")
    ax.set_title("混淆矩阵（测试集）")
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(
                j,
                i,
                str(matrix[i, j]),
                ha="center",
                va="center",
                fontsize=8,
                color="white" if matrix[i, j] > matrix.max() / 2 else "black",
            )
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def train_and_log_model(
    X_train, y_train, X_test, y_test, n_estimators, max_depth, run_name, eval_set
):
    """与实验课同名同结构：训练 -> 评估 -> 记录参数/指标/模型。"""
    with mlflow.start_run(run_name=run_name) as run:
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train.values, y_train.values)
        predictions = model.predict(X_test.values)

        accuracy = accuracy_score(y_test, predictions)
        f1_weighted = f1_score(y_test, predictions, average="weighted")
        f1_macro = f1_score(y_test, predictions, average="macro")
        print(
            f"[{run_name}] n_estimators={n_estimators} max_depth={max_depth} "
            f"accuracy={accuracy:.4f} f1_weighted={f1_weighted:.4f} f1_macro={f1_macro:.4f}"
        )

        # 参数：超参 + 代码版本 + 数据版本（老师要求的两项在这里）
        mlflow.log_param("n_estimators", n_estimators)
        mlflow.log_param("max_depth", max_depth)
        mlflow.log_param("random_state", 42)
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("eval_set", eval_set)
        mlflow.log_param("git_commit", git_commit())
        mlflow.log_param("data_version", data_version())

        # 指标：accuracy 会骗人，所以同时记 weighted / macro F1
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_weighted", f1_weighted)
        mlflow.log_metric("f1_macro", f1_macro)

        # 产物：模型本体（与课件一致）
        mlflow.sklearn.log_model(
            model, name="model", skops_trusted_types=["sklearn.tree._tree.Tree"]
        )

        # 产物：分类报告 + 混淆矩阵
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "classification_report.txt"
            report_path.write_text(
                classification_report(y_test, predictions, digits=4, zero_division=0),
                encoding="utf-8",
            )
            mlflow.log_artifact(str(report_path), artifact_path="reports")

            png_path = Path(tmp) / "confusion_matrix.png"
            labels = [str(c) for c in model.classes_]
            if save_confusion_matrix(y_test, predictions, labels, png_path):
                mlflow.log_artifact(str(png_path), artifact_path="plots")

        metrics = {"accuracy": accuracy, "f1_weighted": f1_weighted, "f1_macro": f1_macro}
        return model, run.info.run_id, metrics


def export_model(model, feature_names, run_id, metrics, eval_set):
    """把生产模型导出成两个文件，供 B 的服务和 C 的镜像直接使用。

    为什么还要单独存一份 joblib：镜像里就不必装 mlflow（几百 MB），启动也更快。
    """
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / "model.joblib", compress=3)

    encoders_path = PROCESSED / "encoders.json"
    meta = {
        "feature_names": list(feature_names),
        "classes": [str(c) for c in model.classes_],
        "mlflow_run_id": run_id,
        "data_version": data_version(),
        "git_commit": git_commit(),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_set": eval_set,
        "metrics": metrics,
        "categorical_encodings": json.loads(encoders_path.read_text(encoding="utf-8"))
        if encoders_path.exists()
        else {},
    }
    (MODELS / "model_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    size_mb = (MODELS / "model.joblib").stat().st_size / 1024 / 1024
    print(f"已导出生产模型：models/model.joblib（{size_mb:.1f}MB）+ models/model_meta.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="训练 NSL-KDD 五分类模型并记录 MLflow")
    parser.add_argument("--config", help="单个配置文件，如 ml/configs/improved.json")
    parser.add_argument("--all", action="store_true", help="跑 ml/configs 下全部配置")
    args = parser.parse_args()

    mlflow.set_tracking_uri((ROOT / "mlruns").resolve().as_uri())
    mlflow.set_experiment(EXPERIMENT)

    X_train, y_train, X_test, y_test, eval_set = load_data()
    print(
        f"训练集 {X_train.shape[0]} 行 / 特征 {X_train.shape[1]} 个；评估集 {len(X_test)} 行（{eval_set}）"
    )

    if args.all:
        configs = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "ml" / "configs").glob("*.json"))
        ]
    elif args.config:
        configs = [json.loads(Path(args.config).read_text(encoding="utf-8"))]
    else:
        parser.error("请使用 --all 或 --config")

    results = []
    for cfg in configs:
        model, run_id, metrics = train_and_log_model(
            X_train,
            y_train,
            X_test,
            y_test,
            n_estimators=cfg["n_estimators"],
            max_depth=cfg["max_depth"],
            run_name=cfg["run_name"],
            eval_set=eval_set,
        )
        results.append((cfg["run_name"], run_id, metrics))

        if cfg.get("promote"):
            export_model(model, X_train.columns, run_id, metrics, eval_set)

    print("\n=== 实验汇总 ===")
    for name, run_id, metrics in results:
        print(
            f"{name:<10} accuracy={metrics['accuracy']:.4f} "
            f"f1_weighted={metrics['f1_weighted']:.4f} f1_macro={metrics['f1_macro']:.4f} "
            f"run_id={run_id}"
        )
    print(f"MLflow 面板：mlflow ui --backend-store-uri {ROOT / 'mlruns'}")


if __name__ == "__main__":
    main()
