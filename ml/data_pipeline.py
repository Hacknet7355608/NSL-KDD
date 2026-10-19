"""NSL-KDD 数据预处理：v1（原始 txt） -> v2（5 分类 + 编码 + 清洗）。

用法（在仓库根目录执行）：
    python ml/data_pipeline.py --raw data/raw/KDDTrain+.txt --out data/processed

产出（data/processed/）：
    X.csv              41 列特征（自动删除全常量列），float64
    y.csv              单列 label，5 个类别：normal / DoS / Probe / R2L / U2R
    encoders.json      3 个类别特征的 字符串->整数 映射（API 必须用同一份映射）
    dataset_stats.json 行数、列数、类别分布、删除的列、原始文件 sha256
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

# NSL-KDD 官方 41 个特征（顺序不能改，KDDTrain+.txt 没有表头）
FEATURES = [
    "duration",
    "protocol_type",
    "service",
    "flag",
    "src_bytes",
    "dst_bytes",
    "land",
    "wrong_fragment",
    "urgent",
    "hot",
    "num_failed_logins",
    "logged_in",
    "num_compromised",
    "root_shell",
    "su_attempted",
    "num_root",
    "num_file_creations",
    "num_shells",
    "num_access_files",
    "num_outbound_cmds",
    "is_host_login",
    "is_guest_login",
    "count",
    "srv_count",
    "serror_rate",
    "srv_serror_rate",
    "rerror_rate",
    "srv_rerror_rate",
    "same_srv_rate",
    "diff_srv_rate",
    "srv_diff_host_rate",
    "dst_host_count",
    "dst_host_srv_count",
    "dst_host_same_srv_rate",
    "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate",
    "dst_host_srv_diff_host_rate",
    "dst_host_serror_rate",
    "dst_host_srv_serror_rate",
    "dst_host_rerror_rate",
    "dst_host_srv_rerror_rate",
]

CATEGORICAL = ["protocol_type", "service", "flag"]
LABEL = "label"
EXTRA = "difficulty"
COLUMNS = FEATURES + [LABEL, EXTRA]

# 39 种攻击 -> 5 大类。KDDTrain+ 里只有 22 种，KDDTest+ 里还有 17 种，
# 提前补全，避免换测试集时因为 map 不全被 dropna() 悄悄丢掉样本。
ATTACK_MAP = {
    "normal": "normal",
    # DoS
    "back": "DoS",
    "land": "DoS",
    "neptune": "DoS",
    "pod": "DoS",
    "smurf": "DoS",
    "teardrop": "DoS",
    "apache2": "DoS",
    "mailbomb": "DoS",
    "processtable": "DoS",
    "udpstorm": "DoS",
    "worm": "DoS",
    # Probe
    "ipsweep": "Probe",
    "nmap": "Probe",
    "portsweep": "Probe",
    "satan": "Probe",
    "mscan": "Probe",
    "saint": "Probe",
    # R2L
    "ftp_write": "R2L",
    "guess_passwd": "R2L",
    "imap": "R2L",
    "multihop": "R2L",
    "phf": "R2L",
    "spy": "R2L",
    "warezclient": "R2L",
    "warezmaster": "R2L",
    "httptunnel": "R2L",
    "named": "R2L",
    "sendmail": "R2L",
    "snmpgetattack": "R2L",
    "snmpguess": "R2L",
    "xlock": "R2L",
    "xsnoop": "R2L",
    # U2R
    "buffer_overflow": "U2R",
    "loadmodule": "U2R",
    "perl": "U2R",
    "rootkit": "U2R",
    "ps": "U2R",
    "sqlattack": "U2R",
    "xterm": "U2R",
    "unknown": "unknown",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"找不到原始数据：{path}\n请先按指导书第 3 步下载 KDDTrain+.txt")
    df = pd.read_csv(path, names=COLUMNS, header=None, skipinitialspace=True)
    if df.shape[1] != len(COLUMNS):
        raise SystemExit(f"列数不对：期望 {len(COLUMNS)} 列，实际 {df.shape[1]} 列")
    return df


def merge_labels(df: pd.DataFrame) -> pd.DataFrame:
    """22/39 种细粒度攻击名 -> 5 大类；出现未知名字直接报错，绝不静默丢样本。"""
    raw = df[LABEL].astype(str).str.strip().str.rstrip(".")
    merged = raw.map(ATTACK_MAP)
    unmapped = sorted(raw[merged.isna()].unique())
    if unmapped:
        raise SystemExit(f"有未映射的攻击类型：{unmapped}，请补到 ATTACK_MAP 里")
    out = df.copy()
    out[LABEL] = merged
    return out


def drop_constant(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """NSL-KDD 里 num_outbound_cmds 恒为 0（is_host_login 也几乎恒为 0），
    常量列对模型没有任何信息量，留着只会让 API 的输入契约变复杂。"""
    constant = [c for c in columns if df[c].nunique(dropna=False) <= 1]
    return df.drop(columns=constant), constant


def encode_categorical(df: pd.DataFrame, maps: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """用“排序后的固定表”编码，而不是 LabelEncoder：
    这样映射是确定的、可以存成 json 交给 API 复用，换数据也不会悄悄变化。

    传入 maps 时按已有映射编码；KDDTest+ 里存在训练集没见过的 service 取值，
    统一编码为 -1（不丢样本、也不臆造含义），并在控制台提示。
    """
    out = df.copy()
    if maps is None:
        maps = {}
        for col in CATEGORICAL:
            values = sorted(out[col].astype(str).str.strip().unique())
            maps[col] = {v: i for i, v in enumerate(values)}
    for col, mapping in maps.items():
        series = out[col].astype(str).str.strip()
        unknown = sorted(set(series.unique()) - set(mapping))
        if unknown:
            print(f"注意：{col} 有 {len(unknown)} 个训练集没见过的取值，编码为 -1：{unknown[:5]}")
        out[col] = series.map(mapping).fillna(-1).astype("int64")
    return out, maps


def main() -> None:
    parser = argparse.ArgumentParser(description="NSL-KDD 预处理")
    parser.add_argument("--raw", default="data/raw/KDDTrain+.txt")
    parser.add_argument("--out", default="data/processed")
    parser.add_argument(
        "--test-raw", default="", help="可选：KDDTest+.txt，用于额外产出 X_test.csv"
    )
    args = parser.parse_args()

    raw_path = Path(args.raw)
    df = load_raw(raw_path)
    rows_in = len(df)

    df = merge_labels(df)
    df, constant_cols = drop_constant(df, FEATURES)
    feature_names = [c for c in FEATURES if c not in constant_cols]
    df, encoders = encode_categorical(df)

    X = df[feature_names].astype("float64")
    y = df[LABEL].astype(str)
    if X.isna().any().any():
        bad = X.columns[X.isna().any()].tolist()
        raise SystemExit(f"以下特征编码后出现空值，检查映射表：{bad}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    X.to_csv(out_dir / "X.csv", index=False)
    y.rename(LABEL).to_csv(out_dir / "y.csv", index=False)
    (out_dir / "encoders.json").write_text(
        json.dumps(encoders, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    stats = {
        "source_file": raw_path.name,
        "source_sha256": sha256_of(raw_path),
        "rows_in": rows_in,
        "rows_out": len(X),
        "features": feature_names,
        "dropped_constant_columns": constant_cols,
        "class_counts": {k: int(v) for k, v in y.value_counts().sort_index().items()},
        "label_map": ATTACK_MAP,
    }
    (out_dir / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.test_raw:
        # 评估集不重新判断常量列：列集合必须与训练集完全一致，直接按 feature_names 取
        test_df = merge_labels(load_raw(Path(args.test_raw)))
        test_df, _ = encode_categorical(test_df, encoders)
        test_df[feature_names].astype("float64").to_csv(out_dir / "X_test.csv", index=False)
        test_df[LABEL].astype(str).rename(LABEL).to_csv(out_dir / "y_test.csv", index=False)
        print(f"额外产出评估集：{len(test_df)} 行")

    print(f"原始 {rows_in} 行 -> 输出 {len(X)} 行 / {len(feature_names)} 个特征")
    print(f"删除常量列：{constant_cols or '无'}")
    print("类别分布：", stats["class_counts"])
    print(f"已写入 {out_dir}/ (X.csv, y.csv, encoders.json, dataset_stats.json)")


if __name__ == "__main__":
    main()
