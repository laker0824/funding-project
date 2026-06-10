"""全市场基金定投策略回测 & 排名（多时间窗口）"""

import pandas as pd
import numpy as np
from datetime import timedelta
import logging
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))
from strategies import run_all_strategies_multi_window, composite_score
import db
import oplog

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
FUND_LIST_PATH = os.path.join(DATA_DIR, "fund_list_filtered.csv")

WINDOWS = (0.25, 0.5, 1, 3, 5, 10)

logger = logging.getLogger("analysis")
if not logger.handlers:
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_sh)
    logger.setLevel(logging.INFO)


def load_fund_list():
    df = pd.read_csv(FUND_LIST_PATH, encoding="utf-8-sig", dtype={"code": str})
    return df


def process_single(code, windows=None, max_retries=2):
    w = windows if windows is not None else WINDOWS
    for _ in range(max_retries):
        try:
            result = run_all_strategies_multi_window(code, windows=w)
            if result is not None:
                return result
        except Exception:
            pass
    return None


def main():
    _t0 = time.time()
    import sys
    windows = tuple(float(a) for a in sys.argv[1:]) if len(sys.argv) > 1 else WINDOWS
    logger.info("=" * 60)
    logger.info("基金定投回测分析系统")
    logger.info("=" * 60)

    fund_list = load_fund_list()
    logger.info("加载基金列表: %d 只", len(fund_list))
    logger.info("回测窗口: %s", ", ".join(f"{w}y" for w in windows))

    nav_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nav")
    codes = [c for c in fund_list["code"].tolist() if os.path.exists(os.path.join(nav_dir, f"{c}.csv"))]
    logger.info("有净值文件的基金: %d 只", len(codes))

    logger.info("开始全量回测...")
    all_results = []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        res = process_single(code, windows)
        if res is not None:
            all_results.append(res)
        if i % 100 == 0 or i == total:
            logger.info("回测进度: %d/%d只", i, total)

    if not all_results:
        logger.warning("无有效结果")
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
    logger.info("排名已保存: %s", out_path)

    # ---- 按窗口打印 Top 10 ----
    for w in sorted(df_best["window"].unique()):
        subset = df_best[df_best["window"] == w].head(10)
        logger.info("=" * 60)
        logger.info("定投最优基金 Top 10 (%s)", w)
        logger.info("=" * 60)
        for i, (_, row) in enumerate(subset.iterrows(), 1):
            logger.info("%2d. %s (%s)", i, row["name"], row["code"])
            logger.info("    类型: %s  |  策略: %s", row["fund_type"], row["strategy"])
            logger.info("    年化: %+.2f%%  评分: %.2f", row["annualized_return_pct"], row["score"])

    # ---- 策略分布 ----
    logger.info("=" * 60)
    logger.info("策略分布统计 (各窗口)")
    logger.info("=" * 60)
    for w in sorted(df_best["window"].unique()):
        subset = df_best[df_best["window"] == w]
        strat_stats = subset["strategy"].value_counts()
        logger.info("[%s] 共 %d 只:", w, len(subset))
        for s, c in strat_stats.items():
            avg_ret = subset[subset["strategy"] == s]["annualized_return_pct"].mean()
            logger.info("    %s: %4d 只 | 平均年化 %+.2f%%", s, c, avg_ret)

    # ---- 策略详情 ----
    detail_path = os.path.join(DATA_DIR, "dca_strategy_detail.csv")
    df_all.to_csv(detail_path, index=False, encoding="utf-8-sig")
    logger.info("策略明细已保存: %s", detail_path)

    # ---- 写入数据库（增量合并） ----
    db.init_db()
    rank_cols = ["code", "window", "name", "fund_type", "strategy",
                 "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
                 "win_rate_pct", "total_return_pct", "vs_lump_sum_pct", "score"]
    if scale_col == "规模(亿)":
        df_best_save = df_best.rename(columns={"规模(亿)": "scale"})
    else:
        df_best_save = df_best.copy()
    df_best_save = df_best_save[rank_cols + (["scale"] if "scale" not in rank_cols else [])]

    existing_rank = db.get_ranking()
    if len(existing_rank):
        existing_rank = existing_rank[~existing_rank["window"].isin(df_best_save["window"].unique())]
        df_best_save = pd.concat([existing_rank, df_best_save], ignore_index=True)
    db.save_ranking(df_best_save)

    existing_detail = db.get_detail()
    if len(existing_detail):
        existing_detail = existing_detail[~existing_detail["window"].isin(df_all["window"].unique())]
        df_all = pd.concat([existing_detail, df_all], ignore_index=True)
    db.save_detail(df_all)
    logger.info("数据库已更新（增量合并）")

    total_windows = df_best.groupby("window")["code"].nunique()
    logger.info("各窗口基金数: %s", dict(total_windows))

    _dur = time.time() - _t0
    _m, _s = divmod(int(_dur), 60)
    _h, _m = divmod(_m, 60)
    logger.info("总耗时: %dh%02dm%02ds", _h, _m, _s)
    oplog.log_backtest(
        windows=len(windows), funds_count=len(codes),
        duration_s=_dur,
        summary=f"windows_detail={dict(total_windows)}",
    )
    logger.info("操作已记录到日志")


if __name__ == "__main__":
    main()
