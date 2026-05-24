import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import subprocess
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from strategies import run_all_strategies, generate_schedule, run_backtest
from strategies import (
    strategy_regular, strategy_ma_deviation, strategy_drawdown,
    strategy_take_profit, strategy_ma_stop, strategy_value_average,
    composite_score, load_nav
)
from viz import (
    _setup_font, _get_font, plot_strategy_pie, plot_risk_return_scatter,
    plot_type_metrics_comparison, plot_vs_lump_sum, plot_strategy_curves,
    VIZ_DIR
)
from analysis_categories import type_strategy_distribution
import db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

st.set_page_config(page_title="基金定投分析系统", layout="wide")
_setup_font()

BASE_AMOUNT = 1000

CN = {
    "code": "代码", "name": "名称", "fund_type": "类型", "规模(亿)": "规模(亿)",
    "strategy": "策略", "annualized_return_pct": "年化收益", "max_drawdown_pct": "最大回撤",
    "sharpe_ratio": "夏普比率", "win_rate_pct": "胜率", "total_return_pct": "总收益",
    "vs_lump_sum_pct": "超一次性", "score": "评分", "total_invested": "总投资",
    "final_value": "终值", "lump_sum_return_pct": "一次性收益",
    "calmar_ratio": "卡玛比率", "years": "年数", "invest_count": "定投次数",
    "date": "日期", "nav": "净值", "acc_nav": "累计净值",
    "avg_excess": "平均超额", "beat_pct": "跑赢比例", "基金类型": "基金类型",
    "基金数量": "基金数量", "跑赢比例(%)": "跑赢比例(%)", "平均超额(%)": "平均超额(%)",
}

_CN_SATURATED = {v: k for k, v in CN.items()}  # reverse not used

def df_cn(df, columns=None):
    df = df.copy()
    if columns:
        keep = [c for c in columns if c in df.columns]
        df = df[keep]
    return df.rename(columns=CN)

STRATEGY_CONFIG = {
    "定期定额(月)": {
        "fn": strategy_regular,
        "params": {"amount": (100, 10000, 1000)},
    },
    "定期定额(周)": {
        "fn": strategy_regular,
        "params": {"amount": (25, 2500, 250)},
    },
    "止盈策略": {
        "fn": strategy_take_profit,
        "params": {"amount": (100, 10000, 1000), "profit_target": (0.05, 0.5, 0.2)},
    },
    "均线偏离法": {
        "fn": strategy_ma_deviation,
        "params": {
            "base_amount": (100, 10000, 1000),
            "ma_period": (60, 250, 120),
            "multiplier": (0.5, 5.0, 2.0),
            "max_mult": (1.0, 10.0, 3.0),
        },
    },
    "回撤加仓法": {
        "fn": strategy_drawdown,
        "params": {
            "base_amount": (100, 10000, 1000),
            "threshold": (0.01, 0.5, 0.1),
            "add_ratio": (0.1, 5.0, 1.0),
        },
    },
    "MA停投法": {
        "fn": strategy_ma_stop,
        "params": {
            "base_amount": (100, 10000, 1000),
            "ma_period": (60, 250, 120),
            "stop_deviation": (0.02, 0.5, 0.15),
        },
    },
    "价值平均法": {
        "fn": strategy_value_average,
        "params": {"base_amount": (100, 10000, 1000), "target_growth": (0.001, 0.05, 0.01)},
    },
}


@st.cache_data
def load_rank(window=None):
    return db.get_ranking(window)


@st.cache_data
def load_detail(window=None):
    return db.get_detail(window)


@st.cache_data
def load_fund_info(code):
    return db.get_fund_info(code)


def fig_to_png(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    return buf


# ── 顶部导航 ──
pages = ["🏠 全市场概况", "🔍 基金分析", "⚙️ 参数调优", "📊 分类分析"]
choice = st.sidebar.selectbox("导航", pages)

# ── 时间窗口选择 ──
WINDOW_OPTIONS = ["1y", "3y", "5y", "10y"]
selected_window = st.sidebar.selectbox("回测时间窗口", WINDOW_OPTIONS, index=1)

def run_update(steps="all", output_area=None):
    """运行数据更新流程"""
    results = []
    python = sys.executable
    root = os.path.dirname(os.path.dirname(__file__))

    if steps in ("all", "downloader"):
        results.append(("下载净值数据", subprocess.run(
            [python, "src/downloader.py"], capture_output=True, text=True,
            timeout=1800, cwd=root)))
    if steps in ("all", "analysis"):
        results.append(("全量回测分析", subprocess.run(
            [python, "src/analysis.py"], capture_output=True, text=True,
            timeout=3600, cwd=root)))
    return results

st.sidebar.markdown("---")
st.sidebar.markdown("**基金定投分析系统 v2.0**")
try:
    rank_count = len(db.get_ranking(selected_window))
except Exception:
    rank_count = "?"
st.sidebar.markdown(f"数据: {rank_count}只基金 × 7策略 @ {selected_window}")

with st.sidebar.expander("🔄 数据更新", expanded=False):
    if st.button("更新净值数据", use_container_width=True):
        with st.spinner("下载中 (耗时约3-15分钟)..."):
            r = run_update("downloader")
            out = r[0][1]
            st.text_area("下载输出", out.stdout[-2000:] + out.stderr[-2000:], height=200)
            st.caption(f"返回值: {out.returncode}")
        st.cache_data.clear()
        st.rerun()

    if st.button("全量回测分析", use_container_width=True):
        with st.spinner("回测中 (耗时约5-20分钟)..."):
            r = run_update("analysis")
            out = r[0][1]
            st.text_area("回测输出", out.stdout[-2000:] + out.stderr[-2000:], height=200)
            st.caption(f"返回值: {out.returncode}")
        st.cache_data.clear()
        st.rerun()

    if st.button("一键全更新 (下载+回测)", type="primary", use_container_width=True):
        with st.spinner("正在下载净值数据..."):
            r1 = run_update("downloader")
            out1 = r1[0][1]
            st.text_area("下载输出", out1.stdout[-1500:] + out1.stderr[-500:], height=150)
        with st.spinner("正在全量回测..."):
            r2 = run_update("analysis")
            out2 = r2[0][1]
            st.text_area("回测输出", out2.stdout[-1500:] + out2.stderr[-500:], height=150)
        st.cache_data.clear()
        st.success(f"更新完成! 下载返回{out1.returncode}, 回测返回{out2.returncode}")
        st.rerun()

st.sidebar.markdown(f"环境: Python {sys.version[:5]}")

if choice == pages[0]:
    st.title("🏠 全市场基金定投概况")
    rank = load_rank(selected_window)
    detail = load_detail(selected_window)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("基金总数", f"{len(rank)} 只")
    col2.metric("策略总数", f"{detail['strategy'].nunique()} 种")
    col3.metric("记录数", f"{len(detail)} 条")
    current_year = datetime.now().year
    interval = int(selected_window.replace("y", ""))
    col4.metric("数据区间", f"{current_year - interval}-{current_year}")

    st.subheader("最优策略分布")
    fig = plot_strategy_pie(rank, save=False, show=False)
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("各类型基金绩效对比")
    fig = plot_type_metrics_comparison(rank, save=False, show=False)
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("定投 vs 一次性投入")
    fig = plot_vs_lump_sum(rank, save=False, show=False)
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("风险-收益散点图")
    fig = plot_risk_return_scatter(rank, save=False, show=False)
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("全市场排名 Top 30")
    cols = ["code", "name", "fund_type", "strategy", "annualized_return_pct",
            "max_drawdown_pct", "sharpe_ratio", "score"]
    st.dataframe(df_cn(rank.head(30), cols).style
                 .format({"年化收益": "{:+.2f}%",
                          "最大回撤": "{:.2f}%",
                          "夏普比率": "{:.3f}",
                          "评分": "{:.2f}"}),
                 width='stretch')

elif choice == pages[1]:
    st.title("🔍 基金深度分析")

    rank = load_rank(selected_window)
    col1, col2 = st.columns([1, 3])
    fund_options = rank[["code", "name"]].head(50).copy()
    fund_options["code"] = fund_options["code"].astype(str)
    fund_options["label"] = fund_options["code"] + " - " + fund_options["name"]
    options_map = dict(zip(fund_options["label"], fund_options["code"]))

    selected_label = col1.selectbox("选择基金（前50名）", options_map.keys())
    manual_code = col1.text_input("或直接输入基金代码", "")

    use_fee = col1.checkbox("计入交易费用", value=False)
    buy_fee = col1.slider("申购费率", 0.0, 0.015, 0.0015, 0.0005) if use_fee else 0.0
    sell_fee = col1.slider("赎回费率", 0.0, 0.015, 0.005, 0.0005) if use_fee else 0.0

    fund_code = manual_code.strip() if manual_code.strip() else options_map[selected_label]

    if col1.button("运行分析"):
        window_years = int(selected_window.replace("y", ""))
        with st.spinner(f"正在回测 {fund_code} ({selected_window})..."):
            result = run_all_strategies(fund_code, years=window_years,
                                        buy_fee_rate=buy_fee, sell_fee_rate=sell_fee)

        if result is None:
            st.error("回测失败：数据不足或净值文件缺失")
        else:
            info = load_fund_info(fund_code)
            if info is not None:
                scale = info.get("scale", info.get("规模(亿)", 0))
                st.info(f"**{info['name']}** ｜ 类型: {info['fund_type']} ｜ 规模: {scale:.1f}亿")

            result["score"] = result.apply(composite_score, axis=1)
            result = result.sort_values("score", ascending=False)

            st.subheader("策略对比")
            display_cols = ["strategy", "annualized_return_pct", "max_drawdown_pct",
                            "sharpe_ratio", "win_rate_pct", "total_return_pct",
                            "vs_lump_sum_pct", "total_invested", "final_value", "score"]
            st.dataframe(df_cn(result, display_cols).style
                         .format({"年化收益": "{:+.2f}%",
                                  "最大回撤": "{:.2f}%",
                                  "夏普比率": "{:.3f}",
                                  "胜率": "{:.1f}%",
                                  "总收益": "{:+.2f}%",
                                  "超一次性": "{:+.2f}%",
                                  "总投资": "{:.0f}",
                                  "终值": "{:.0f}",
                                  "评分": "{:.2f}"}),
                         width='stretch')

            # 最佳策略
            best = result.iloc[0]
            st.success(f"最佳策略: **{best['strategy']}** ｜ 年化收益 {best['annualized_return_pct']:+.2f}% ｜ "
                       f"超一次性 {best['vs_lump_sum_pct']:+.2f}% ｜ 评分 {best['score']:.2f}")

            # 图表
            st.subheader("资金曲线")
            nav_df = load_nav(fund_code)
            window_years = int(selected_window.replace("y", ""))
            sched = generate_schedule(nav_df["date"], nav_df["date"].max() - pd.DateOffset(years=window_years),
                                      nav_df["date"].max(), freq="M", day=1)

            fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

            axes[0].plot(nav_df[nav_df["date"] >= nav_df["date"].max() - pd.DateOffset(years=window_years)]["date"],
                         nav_df[nav_df["date"] >= nav_df["date"].max() - pd.DateOffset(years=window_years)]["nav"],
                         color="black", linewidth=1.5, label="净值(NAV)")
            colors = plt.cm.tab10(np.linspace(0, 1, len(result)))
            for idx, (_, row) in enumerate(result.iterrows()):
                axes[0].plot([], [], color=colors[idx], label=f"{row['strategy']} ({row['annualized_return_pct']:+.1f}%)")
            axes[0].set_title("策略资金曲线（仅显示标签，详情见数据表）")
            axes[0].legend(prop=_get_font(8), ncol=2)
            axes[0].grid(True, alpha=0.3)

            for idx, (_, row) in enumerate(result.iterrows()):
                sfn = {
                    "定期定额(月)": strategy_regular(BASE_AMOUNT),
                    "定期定额(周)": strategy_regular(BASE_AMOUNT / 4),
                    "均线偏离法": strategy_ma_deviation(BASE_AMOUNT),
                    "回撤加仓法": strategy_drawdown(BASE_AMOUNT),
                    "止盈策略(20%)": strategy_take_profit(BASE_AMOUNT),
                    "MA停投法": strategy_ma_stop(BASE_AMOUNT),
                    "价值平均法": strategy_value_average(BASE_AMOUNT),
                }.get(row["strategy"])
                if sfn:
                    _, rd = run_backtest(nav_df, sched, sfn, row["strategy"])
                    if len(rd) > 0:
                        axes[1].fill_between(rd["date"], rd["value"] - rd["invested"], 0, alpha=0.15)
                        axes[1].plot(rd["date"], rd["value"] - rd["invested"],
                                     color=colors[idx], linewidth=1, label=row["strategy"])

            axes[1].axhline(y=0, color="red", linestyle="--", linewidth=0.5)
            axes[1].set_title("各策略累计收益")
            axes[1].legend(prop=_get_font(8), ncol=2)
            axes[1].grid(True, alpha=0.3)

            plt.tight_layout()
            st.pyplot(fig)
            plt.close()

            nav_df = load_nav(fund_code)
            if os.path.exists(os.path.join(DATA_DIR, "nav", f"{fund_code}.csv")):
                st.subheader("净值数据预览")
                st.dataframe(df_cn(nav_df.tail(30), ["date", "nav", "acc_nav"])
                             .style.format({"净值": "{:.4f}", "累计净值": "{:.4f}"}),
                             width='stretch')

elif choice == pages[2]:
    st.title("⚙️ 策略参数调优")

    rank = load_rank(selected_window)
    strategy_name = st.selectbox("选择策略", list(STRATEGY_CONFIG.keys()))

    config = STRATEGY_CONFIG[strategy_name]
    param_vals = {}
    for pname, (pmin, pmax, pdefault) in config["params"].items():
        is_int = isinstance(pmin, int) and isinstance(pmax, int)
        if is_int:
            param_vals[pname] = st.sidebar.slider(
                pname, int(pmin), int(pmax), int(pdefault),
                step=1, format="%d"
            )
        else:
            param_vals[pname] = st.sidebar.slider(
                pname, float(pmin), float(pmax), float(pdefault),
                format="%.3f"
            )

    n_funds = st.sidebar.slider("样本基金数量", 10, 200, 50)
    test_codes = rank.head(n_funds)["code"].tolist()

    with_fee = st.sidebar.checkbox("含交易费用", value=False)
    buy_fee = st.sidebar.slider("申购费率", 0.0, 0.015, 0.0015, 0.0005) if with_fee else 0.0
    sell_fee = st.sidebar.slider("赎回费率", 0.0, 0.015, 0.005, 0.0005) if with_fee else 0.0

    if st.button("开始调优"):
        fn = config["fn"](**param_vals)
        results = []
        progress = st.progress(0)

        for i, code in enumerate(test_codes):
            nav_df = load_nav(code)
            if nav_df is None or len(nav_df) < 300:
                progress.progress((i + 1) / len(test_codes))
                continue
            window_years = int(selected_window.replace("y", ""))
            start_date = nav_df["date"].max() - pd.DateOffset(years=window_years)
            end_date = nav_df["date"].max()
            mask = (nav_df["date"] >= start_date) & (nav_df["date"] <= end_date)
            nav_period = nav_df[mask].copy().reset_index(drop=True)
            if len(nav_period) < 250:
                progress.progress((i + 1) / len(test_codes))
                continue
            sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
            try:
                metrics, _ = run_backtest(nav_period, sched, fn, strategy_name,
                                          buy_fee_rate=buy_fee, sell_fee_rate=sell_fee)
                if metrics and metrics.get("annualized_return_pct", 0) != 0:
                    score = composite_score(metrics)
                    results.append({"code": code, "strategy": strategy_name,
                                    **param_vals, "score": score, **metrics})
            except Exception:
                pass
            progress.progress((i + 1) / len(test_codes))

        if not results:
            st.warning("无有效结果")
            st.stop()

        df = pd.DataFrame(results)
        avg = {k: df[k].mean() for k in ["annualized_return_pct", "max_drawdown_pct",
                                           "sharpe_ratio", "win_rate_pct", "score"]}

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("样本基金", len(df))
        col2.metric("平均年化", f"{avg['annualized_return_pct']:+.2f}%")
        col3.metric("平均回撤", f"{avg['max_drawdown_pct']:.2f}%")
        col4.metric("平均夏普", f"{avg['sharpe_ratio']:.3f}")
        col5.metric("平均评分", f"{avg['score']:.2f}")

        fund_list = pd.read_csv(os.path.join(DATA_DIR, "fund_list_filtered.csv"),
                               encoding="utf-8-sig", dtype={"code": str})
        df = df.merge(fund_list[["code", "name"]], on="code", how="left")

        st.dataframe(df_cn(df, ["code", "name", "annualized_return_pct", "max_drawdown_pct",
                                "sharpe_ratio", "win_rate_pct", "total_return_pct", "score"])
                     .style.format({"年化收益": "{:+.2f}%",
                                    "最大回撤": "{:.2f}%",
                                    "夏普比率": "{:.3f}",
                                    "胜率": "{:.1f}%",
                                    "总收益": "{:+.2f}%",
                                    "评分": "{:.2f}"}),
                     width='stretch')

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].hist(df["annualized_return_pct"], bins=20, edgecolor="white", color="steelblue")
        axes[0].set_xlabel("年化收益(%)")
        axes[0].set_ylabel("基金数量")
        axes[0].set_title(f"{strategy_name} 年化收益分布")
        axes[0].axvline(avg["annualized_return_pct"], color="red", linestyle="--", label=f"均值 {avg['annualized_return_pct']:+.1f}%")
        axes[0].legend()

        axes[1].scatter(df["max_drawdown_pct"], df["annualized_return_pct"],
                       c=df["score"], cmap="viridis", alpha=0.6, s=40)
        axes[1].set_xlabel("最大回撤(%)")
        axes[1].set_ylabel("年化收益(%)")
        axes[1].set_title("风险-收益 散点图")
        cbar = plt.colorbar(axes[1].collections[0], ax=axes[1])
        cbar.set_label("评分")

        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

elif choice == pages[3]:
    st.title("📊 分类分析")

    rank = load_rank(selected_window)
    detail = load_detail(selected_window)

    st.subheader("各类型基金最优策略分布")
    cross = pd.crosstab(rank["fund_type"], rank["strategy"], margins=True, margins_name="合计")
    cross.index.name = "基金类型"
    cross.columns.name = "策略"
    st.dataframe(cross, width='stretch')

    st.subheader("各类型基金平均绩效")
    metrics = ["annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
               "win_rate_pct", "total_return_pct", "vs_lump_sum_pct", "score"]
    grouped = rank.groupby("fund_type")[metrics].mean().round(2)
    grouped.index.name = "类型"
    grouped.columns = pd.Index(["年化收益", "最大回撤", "夏普比率", "胜率",
                                "总收益", "超一次性", "评分"])
    st.dataframe(grouped.style
                 .format({k: "{:+.2f}" if k in ("年化收益", "总收益", "超一次性") else "{:.2f}"
                          for k in grouped.columns}),
                 width='stretch')

    st.subheader("跑赢一次性投入比例")
    beat_data = []
    for ftype in rank["fund_type"].unique():
        subset = rank[rank["fund_type"] == ftype]
        beat_data.append({
            "基金类型": ftype,
            "基金数量": len(subset),
            "跑赢比例(%)": round((subset["vs_lump_sum_pct"] > 0).mean() * 100, 1),
            "平均超额(%)": round(subset["vs_lump_sum_pct"].mean(), 2),
        })
    st.dataframe(pd.DataFrame(beat_data), width='stretch')

    st.subheader("各策略在全部基金上的平均表现")
    detail_metrics = ["annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
                      "win_rate_pct", "total_return_pct", "vs_lump_sum_pct"]
    detail_grouped = detail.groupby("strategy")[detail_metrics].mean().round(2)
    st.dataframe(df_cn(detail_grouped.reset_index()).set_index("策略").style
                 .format("{:+.2f}" if m in ("年化收益", "总收益", "超一次性") else "{:.2f}"
                         for m in detail_grouped.columns),
                 width='stretch')

    st.subheader("策略间相关性（年化收益）")
    pivot = detail.pivot_table(index="code", columns="strategy", values="annualized_return_pct")
    corr = pivot.corr().round(3)
    st.dataframe(corr, width='stretch')
