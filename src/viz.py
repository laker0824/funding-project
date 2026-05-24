import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties, fontManager
import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from strategies import run_all_strategies, load_nav, run_backtest, generate_schedule
from strategies import strategy_regular, strategy_ma_deviation, strategy_drawdown
from strategies import strategy_take_profit, strategy_ma_stop, strategy_value_average

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VIZ_DIR = os.path.join(DATA_DIR, "charts")
os.makedirs(VIZ_DIR, exist_ok=True)

_font_set = False
_cn_font = None


def _find_cn_font():
    for f in fontManager.ttflist:
        name = f.name.lower()
        if any(fn in name for fn in ["yahei", "simhei", "dengxian", "noto sans sc"]):
            return f.name
    for f in fontManager.ttflist:
        name = f.name.lower()
        if any(fn in name for fn in ["hei", "song", "kai", "fang", "yuan", "ming", "cjk"]):
            return f.name
    return "DejaVu Sans"


def _setup_font():
    global _font_set, _cn_font
    if _font_set:
        return
    _cn_font = _find_cn_font()
    plt.rcParams["font.family"] = _cn_font
    plt.rcParams["axes.unicode_minus"] = False
    _font_set = True


def _get_font(size=10):
    _setup_font()
    return FontProperties(family=_cn_font, size=size)


def plot_strategy_curves(fund_code, fund_name="", save=True, show=True):
    nav_df = load_nav(fund_code)
    if nav_df is None or len(nav_df) < 300:
        print(f"基金 {fund_code} 净值数据不足")
        return

    start_date = nav_df["date"].max() - pd.DateOffset(years=3)
    end_date = nav_df["date"].max()
    mask = (nav_df["date"] >= start_date) & (nav_df["date"] <= end_date)
    nav_period = nav_df[mask].copy().reset_index(drop=True)
    if len(nav_period) < 250:
        print(f"基金 {fund_code} 回测期数据不足")
        return

    base_monthly = 1000
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)

    strategies = [
        ("定期定额", strategy_regular(base_monthly)),
        ("均线偏离法", strategy_ma_deviation(base_monthly)),
        ("回撤加仓法", strategy_drawdown(base_monthly)),
        ("止盈策略", strategy_take_profit(base_monthly)),
        ("MA停投法", strategy_ma_stop(base_monthly)),
        ("价值平均法", strategy_value_average(base_monthly)),
    ]

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    ax1, ax2, ax3 = axes

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
              "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

    ax1.plot(nav_period["date"], nav_period["nav"], color="black", linewidth=1.5, label="净值(NAV)")
    for idx, (sname, sfn) in enumerate(strategies):
        metrics, result_df = run_backtest(nav_period, sched, sfn, sname)
        ax1.plot(result_df["date"], result_df["value"], color=colors[idx % len(colors)],
                 linewidth=1, alpha=0.8, label=f"{sname}({metrics['annualized_return_pct']:+.1f}%)")

    ax1.set_ylabel("金额/净值")
    ax1.set_title(f"{fund_name or fund_code} — 各策略资金曲线对比")
    ax1.legend(prop=_get_font(8), loc="upper left", ncol=2)
    ax1.grid(True, alpha=0.3)

    for idx, (sname, sfn) in enumerate(strategies):
        metrics, result_df = run_backtest(nav_period, sched, sfn, sname)
        values = result_df["value"].values
        peak = np.maximum.accumulate(values)
        safe = np.where(peak == 0, 1, peak)
        dd = (safe - values) / safe * 100
        ax2.fill_between(result_df["date"], dd, 0, color=colors[idx % len(colors)],
                         alpha=0.3)
        ax2.plot(result_df["date"], dd, color=colors[idx % len(colors)],
                 linewidth=0.8, label=sname)

    ax2.set_ylabel("回撤(%)")
    ax2.set_title("各策略回撤曲线")
    ax2.legend(prop=_get_font(8), loc="lower left", ncol=2)
    ax2.grid(True, alpha=0.3)
    ax2.invert_yaxis()

    for idx, (sname, sfn) in enumerate(strategies):
        metrics, result_df = run_backtest(nav_period, sched, sfn, sname)
        invest_df = result_df[result_df["amount"] > 0]
        if len(invest_df) > 0:
            ax3.bar(invest_df["date"], invest_df["amount"],
                    color=colors[idx % len(colors)], alpha=0.5, width=5, label=sname)

    ax3.set_ylabel("投入金额(元)")
    ax3.set_xlabel("日期")
    ax3.set_title("各策略每月投入金额")
    ax3.legend(prop=_get_font(8), loc="upper left", ncol=2)
    ax3.grid(True, alpha=0.3)

    plt.xticks(rotation=45)
    plt.tight_layout()

    if save:
        safe_name = fund_code if fund_code.isdigit() else fund_code.split(".")[0]
        path = os.path.join(VIZ_DIR, f"{safe_name}_strategies.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {path}")

    if show:
        plt.show()
    return plt.gcf()


def plot_strategy_pie(rank_df, save=True, show=True):
    _setup_font()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax1, ax2 = axes

    counts = rank_df["strategy"].value_counts()
    colors = plt.cm.Set3(np.linspace(0, 1, len(counts)))
    ax1.pie(counts.values, labels=counts.index, autopct="%1.1f%%",
            colors=colors, startangle=90, textprops={"fontproperties": _get_font(10)})
    ax1.set_title("全部基金最优策略分布", fontproperties=_get_font(12))

    type_counts = rank_df["fund_type"].value_counts()
    colors2 = plt.cm.Pastel1(np.linspace(0, 1, len(type_counts)))
    ax2.pie(type_counts.values, labels=type_counts.index, autopct="%1.1f%%",
            colors=colors2, startangle=90, textprops={"fontproperties": _get_font(10)})
    ax2.set_title("基金类型分布", fontproperties=_get_font(12))

    plt.tight_layout()
    if save:
        path = os.path.join(VIZ_DIR, "strategy_type_distribution.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {path}")
    if show:
        plt.show()
    return fig


def plot_risk_return_scatter(rank_df, save=True, show=True):
    _setup_font()
    fig, ax = plt.subplots(figsize=(10, 7))
    types = rank_df["fund_type"].unique()
    colors = plt.cm.tab10(np.linspace(0, 1, len(types)))
    for ftype, color in zip(types, colors):
        subset = rank_df[rank_df["fund_type"] == ftype].dropna(subset=["max_drawdown_pct", "annualized_return_pct", "score"])
        if len(subset) == 0:
            continue
        sizes = subset["score"].fillna(0).clip(lower=10) * 5
        scatter = ax.scatter(subset["max_drawdown_pct"], subset["annualized_return_pct"],
                             c=[color], alpha=0.6, s=sizes,
                             label=f"{ftype}({len(subset)})")
    ax.set_xlabel("最大回撤(%)", fontproperties=_get_font(10))
    ax.set_ylabel("年化收益(%)", fontproperties=_get_font(10))
    ax.set_title("风险-收益散点图（气泡大小=综合评分）", fontproperties=_get_font(12))
    ax.legend(prop=_get_font(9), loc="upper right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if save:
        path = os.path.join(VIZ_DIR, "risk_return_scatter.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {path}")
    if show:
        plt.show()
    return fig


def plot_type_metrics_comparison(rank_df, save=True, show=True):
    _setup_font()
    metrics = ["annualized_return_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate_pct"]
    labels = ["年化收益(%)", "最大回撤(%)", "夏普比率", "胜率(%)"]

    grouped = rank_df.groupby("fund_type")[metrics].mean()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    colors = plt.cm.Set2(np.linspace(0, 1, len(grouped)))
    for ax, metric, label in zip(axes.flat, metrics, labels):
        bars = ax.bar(grouped.index, grouped[metric], color=colors, edgecolor="grey", alpha=0.8)
        ax.set_title(label, fontproperties=_get_font(12))
        ax.set_xticks(range(len(grouped)))
        ax.set_xticklabels(grouped.index, fontproperties=_get_font(8), rotation=30, ha="right")
        ax.grid(True, alpha=0.3, axis="y")
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.1f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)

    plt.tight_layout()
    if save:
        path = os.path.join(VIZ_DIR, "type_metrics_comparison.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {path}")
    if show:
        plt.show()
    return fig


def plot_vs_lump_sum(rank_df, save=True, show=True):
    _setup_font()
    fig, ax = plt.subplots(figsize=(10, 5))
    types = rank_df["fund_type"].unique()
    data = []
    for ftype in types:
        subset = rank_df[rank_df["fund_type"] == ftype]
        data.append([ftype, subset["vs_lump_sum_pct"].mean(),
                     (subset["vs_lump_sum_pct"] > 0).mean() * 100])
    df = pd.DataFrame(data, columns=["type", "avg_excess", "beat_pct"])

    x = range(len(df))
    bars = ax.bar(x, df["avg_excess"], color=plt.cm.Paired(np.linspace(0, 1, len(df))),
                  edgecolor="grey", alpha=0.8)
    ax.axhline(y=0, color="red", linestyle="--", linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(df["type"], fontproperties=_get_font(9), rotation=30, ha="right")
    ax.set_ylabel("平均超额收益(%)", fontproperties=_get_font(10))
    ax.set_title("各类型基金定投 vs 一次性投入（超额收益 + 跑赢比例）", fontproperties=_get_font(12))
    ax.grid(True, alpha=0.3, axis="y")

    for bar, beat in zip(bars, df["beat_pct"]):
        height = bar.get_height()
        offset = 1.5 if height >= 0 else -8
        ax.annotate(f"跑赢{beat:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, offset), textcoords="offset points", ha="center", fontsize=9,
                    color="green" if beat > 50 else "red")

    plt.tight_layout()
    if save:
        path = os.path.join(VIZ_DIR, "vs_lump_sum.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"图表已保存: {path}")
    if show:
        plt.show()
    return fig


if __name__ == "__main__":
    import db
    rank = db.get_ranking()
    print(f"加载 {len(rank)} 条排名数据")

    plot_strategy_pie(rank, show=False)
    plot_risk_return_scatter(rank, show=False)
    plot_type_metrics_comparison(rank, show=False)
    plot_vs_lump_sum(rank, show=False)

    for code in ["960033", "110011", "510300"]:
        plot_strategy_curves(code, fund_name=code, show=False)
