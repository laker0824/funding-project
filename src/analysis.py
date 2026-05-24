"""全市场基金定投策略回测 & 排名（多时间窗口）"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))
from strategies import run_all_strategies_multi_window, composite_score
from db import save_ranking, save_detail, init_db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
FUND_LIST_PATH = os.path.join(DATA_DIR, "fund_list_filtered.csv")

WINDOWS = (1, 3, 5, 10)


def load_fund_list():
    df = pd.read_csv(FUND_LIST_PATH, encoding="utf-8-sig", dtype={"code": str})
    return df


def process_single(code, max_retries=2):
    for _ in range(max_retries):
        try:
            result = run_all_strategies_multi_window(code, windows=WINDOWS)
            if result is not None:
                return result
        except Exception:
            pass
    return None


def main():
    print("=" * 60)
    print("基金定投回测分析系统")
    print("=" * 60)

    fund_list = load_fund_list()
    print(f"\n加载基金列表: {len(fund_list)} 只")
    print(f"回测窗口: {', '.join(f'{w}y' for w in WINDOWS)}")

    nav_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nav")
    codes = [c for c in fund_list["code"].tolist() if os.path.exists(os.path.join(nav_dir, f"{c}.csv"))]
    print(f"有净值文件的基金: {len(codes)} 只")

    print("\n开始全量回测 (并行30线程)...")
    all_results = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(process_single, code): code for code in codes}
        for f in tqdm(as_completed(futures), total=len(futures), desc="回测进度"):
            try:
                res = f.result()
                if res is not None:
                    all_results.append(res)
            except Exception:
                pass

    if not all_results:
        print("无有效结果")
        return

    df_all = pd.concat(all_results, ignore_index=True)
    df_all["score"] = df_all.apply(composite_score, axis=1)

    # 按 (code, window) 找最佳策略
    best_idx = df_all.groupby(["code", "window"])["annualized_return_pct"].idxmax()
    df_best = df_all.loc[best_idx].copy().reset_index(drop=True)

    # 合并基金信息
    scale_col = "规模(亿)" if "规模(亿)" in fund_list.columns else "scale"
    df_best = df_best.merge(
        fund_list[["code", "name", "fund_type", scale_col]],
        on="code", how="left",
    )

    # 排序
    df_best = df_best.sort_values(["window", "score"], ascending=[True, False]).reset_index(drop=True)

    # ---- 输出结果 ----
    cols_show = ["code", "name", "fund_type", scale_col,
                 "window", "strategy", "annualized_return_pct", "max_drawdown_pct",
                 "sharpe_ratio", "win_rate_pct", "total_return_pct",
                 "vs_lump_sum_pct", "score"]
    out_path = os.path.join(DATA_DIR, "dca_ranking.csv")
    df_best[cols_show].to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n排名已保存: {out_path}")

    # ---- 按窗口打印 Top 10 ----
    for w in sorted(df_best["window"].unique()):
        subset = df_best[df_best["window"] == w].head(10)
        print(f"\n{'=' * 60}")
        print(f"定投最优基金 Top 10 ({w})")
        print("=" * 60)
        for i, (_, row) in enumerate(subset.iterrows(), 1):
            print(f"\n{i:2d}. {row['name']} ({row['code']})")
            print(f"    类型: {row['fund_type']}  |  策略: {row['strategy']}")
            print(f"    年化: {row['annualized_return_pct']:+.2f}%  评分: {row['score']:.2f}")

    # ---- 策略分布 ----
    print("\n" + "=" * 60)
    print("策略分布统计 (各窗口)")
    print("=" * 60)
    for w in sorted(df_best["window"].unique()):
        subset = df_best[df_best["window"] == w]
        strat_stats = subset["strategy"].value_counts()
        print(f"\n  [{w}] 共 {len(subset)} 只:")
        for s, c in strat_stats.items():
            avg_ret = subset[subset["strategy"] == s]["annualized_return_pct"].mean()
            print(f"    {s:16s}: {c:4d} 只 | 平均年化 {avg_ret:+.2f}%")

    # ---- 策略详情 ----
    detail_path = os.path.join(DATA_DIR, "dca_strategy_detail.csv")
    df_all.to_csv(detail_path, index=False, encoding="utf-8-sig")
    print(f"\n策略明细已保存: {detail_path}")

    # ---- 写入数据库 ----
    init_db()
    rank_cols = ["code", "window", "name", "fund_type", "strategy",
                 "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
                 "win_rate_pct", "total_return_pct", "vs_lump_sum_pct", "score"]
    if scale_col == "规模(亿)":
        df_best_save = df_best.rename(columns={"规模(亿)": "scale"})
    else:
        df_best_save = df_best.copy()
    save_ranking(df_best_save[rank_cols + (["scale"] if "scale" not in rank_cols else [])])
    save_detail(df_all)
    print("数据库已更新")

    total_windows = df_best.groupby("window")["code"].nunique()
    print(f"\n各窗口基金数: {dict(total_windows)}")


if __name__ == "__main__":
    main()
