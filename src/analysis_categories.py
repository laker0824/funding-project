import pandas as pd
import numpy as np
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from strategies import composite_score
import db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_results(window="3y"):
    rank = db.get_ranking(window)
    detail = db.get_detail(window)
    return rank, detail


def type_strategy_distribution(rank):
    print("=" * 60)
    print("各类基金最优策略分布")
    print("=" * 60)
    cross = pd.crosstab(rank["fund_type"], rank["strategy"], margins=True, margins_name="合计")
    cross.index.name = "基金类型"
    cross.columns.name = "策略"
    print(cross.to_string())
    print()

    for ftype in rank["fund_type"].unique():
        subset = rank[rank["fund_type"] == ftype]
        best_strat = subset["strategy"].mode().iloc[0]
        best_pct = (subset["strategy"] == best_strat).mean() * 100
        print(f"  {ftype}: 最优={best_strat} ({best_pct:.1f}%),  共{len(subset)}只基金")


def type_avg_metrics(rank):
    print("\n" + "=" * 60)
    print("各类型基金平均绩效指标")
    print("=" * 60)
    metrics = ["annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
               "win_rate_pct", "total_return_pct", "vs_lump_sum_pct", "score"]
    grouped = rank.groupby("fund_type")[metrics].mean().round(2)
    grouped.index.name = "基金类型"
    grouped.columns = pd.Index(["年化收益", "最大回撤", "夏普比率", "胜率",
                                "总收益", "超一次性", "评分"])
    print(grouped.to_string())


def type_vs_lump_sum(rank):
    print("\n" + "=" * 60)
    print("各类型基金定投 vs 一次性投入表现")
    print("=" * 60)
    for ftype in rank["fund_type"].unique():
        subset = rank[rank["fund_type"] == ftype]
        beat = (subset["vs_lump_sum_pct"] > 0).mean() * 100
        avg_vs = subset["vs_lump_sum_pct"].mean()
        print(f"  {ftype}: 跑赢一次性={beat:.1f}%,  平均超额={avg_vs:+.2f}%")


def best_funds_by_type(rank, top_n=10):
    print("\n" + "=" * 60)
    print("各类型评分Top10基金")
    print("=" * 60)
    for ftype in rank["fund_type"].unique():
        subset = rank[rank["fund_type"] == ftype].head(top_n)
        print(f"\n--- {ftype} Top{top_n} ---")
        for i, (_, row) in enumerate(subset.iterrows(), 1):
            print(f"  {i:2d}. {row['name']} | 年化{row['annualized_return_pct']:+.2f}% | {row['strategy']} | 评分{row['score']:.2f}")


def type_winrate_detail(rank):
    print("\n" + "=" * 60)
    print("各类型基金胜率分布")
    print("=" * 60)
    bins = [0, 20, 30, 40, 50, 60, 100]
    labels = ["<20%", "20-30%", "30-40%", "40-50%", "50-60%", ">60%"]
    rank["胜率区间"] = pd.cut(rank["win_rate_pct"], bins=bins, labels=labels)
    cross = pd.crosstab(rank["fund_type"], rank["胜率区间"])
    print(cross.to_string())


def strategy_detail_comparison(detail):
    print("\n" + "=" * 60)
    print("各策略在全部基金上的平均表现")
    print("=" * 60)
    metrics = ["annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
               "win_rate_pct", "total_return_pct", "vs_lump_sum_pct"]
    grouped = detail.groupby("strategy")[metrics].agg(["mean", "std"]).round(2)
    grouped.columns = pd.MultiIndex.from_product(
        [["年化收益", "最大回撤", "夏普比率", "胜率", "总收益", "超一次性"], ["均值", "标准差"]])
    print(grouped.to_string())


def strategy_corr_analysis(detail):
    print("\n" + "=" * 60)
    print("策略间相关性分析（同基金各策略年化收益的皮尔逊相关）")
    print("=" * 60)
    pivot = detail.pivot_table(index="code", columns="strategy",
                               values="annualized_return_pct")
    corr = pivot.corr().round(3)
    print(corr.to_string())


def main():
    import sys
    window = sys.argv[1] if len(sys.argv) > 1 else "3y"
    rank, detail = load_results(window)
    print(f"时间窗口: {window}")
    print(f"读取排名数据: {len(rank)} 只基金")
    print(f"读取策略详情: {len(detail)} 条记录")
    print()

    type_strategy_distribution(rank)
    type_avg_metrics(rank)
    type_vs_lump_sum(rank)
    type_winrate_detail(rank)
    best_funds_by_type(rank, top_n=5)
    strategy_detail_comparison(detail)
    strategy_corr_analysis(detail)


if __name__ == "__main__":
    main()
