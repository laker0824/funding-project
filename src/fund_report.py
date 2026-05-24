import pandas as pd
import numpy as np
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from strategies import run_all_strategies, load_nav, generate_schedule, run_backtest
from strategies import strategy_regular, strategy_ma_deviation, strategy_drawdown
from strategies import strategy_take_profit, strategy_ma_stop, strategy_value_average, composite_score
import viz
import db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def search_fund(keyword):
    fund_list = db.get_funds_df()
    mask = fund_list["code"].str.contains(keyword) | fund_list["name"].str.contains(keyword)
    return fund_list[mask]


def print_strategy_table(strategies_result):
    print(f"\n{'策略':20s} {'年化收益':>10s} {'总收益':>10s} {'最大回撤':>10s} {'夏普':>8s} {'胜率':>8s} {'总投资':>10s} {'终值':>10s} {'超一次性':>10s} {'评分':>8s}")
    print("-" * 114)
    for _, row in strategies_result.iterrows():
        score = composite_score(row)
        print(f"{row['strategy']:20s} {row['annualized_return_pct']:>+9.2f}% "
              f"{row['total_return_pct']:>+9.2f}% {row['max_drawdown_pct']:>9.2f}% "
              f"{row['sharpe_ratio']:>8.3f} {row['win_rate_pct']:>7.1f}% "
              f"{row['total_invested']:>10.0f} {row['final_value']:>10.0f} "
              f"{row['vs_lump_sum_pct']:>+9.2f}% {score:>8.2f}")


def print_best_strategy_detail(code, strategies_result):
    best_idx = strategies_result["annualized_return_pct"].idxmax()
    best = strategies_result.loc[best_idx]
    print(f"\n{'=' * 60}")
    print(f"最佳策略: {best['strategy']}")
    print(f"年化收益: {best['annualized_return_pct']:+.2f}%")
    print(f"总收益:   {best['total_return_pct']:+.2f}%")
    print(f"最大回撤: {best['max_drawdown_pct']:.2f}%")
    print(f"夏普比率: {best['sharpe_ratio']:.3f}")
    print(f"胜率:     {best['win_rate_pct']:.1f}%")
    print(f"总投资:   {best['total_invested']:.0f}元")
    print(f"最终价值: {best['final_value']:.0f}元")
    print(f"一次性投入收益: {best['lump_sum_return_pct']:+.2f}%")
    print(f"定投超额收益:   {best['vs_lump_sum_pct']:+.2f}%")


def print_investment_schedule(code, best_strategy_name):
    nav_df = load_nav(code)
    start_date = nav_df["date"].max() - pd.DateOffset(years=3)
    end_date = nav_df["date"].max()
    mask = (nav_df["date"] >= start_date) & (nav_df["date"] <= end_date)
    nav_period = nav_df[mask].copy().reset_index(drop=True)

    base_monthly = 1000
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)

    strategy_map = {
        "定期定额(月)": strategy_regular(base_monthly),
        "定期定额(周)": strategy_regular(base_monthly / 4),
        "均线偏离法": strategy_ma_deviation(base_monthly),
        "回撤加仓法": strategy_drawdown(base_monthly),
        "止盈策略(20%)": strategy_take_profit(base_monthly),
        "MA停投法": strategy_ma_stop(base_monthly),
        "价值平均法": strategy_value_average(base_monthly),
    }

    if best_strategy_name not in strategy_map:
        return

    sfn = strategy_map[best_strategy_name]
    _, result_df = run_backtest(nav_period, sched, sfn, best_strategy_name)

    invest_days = result_df[result_df["amount"] > 0].copy()
    print(f"\n{'=' * 60}")
    print(f"{best_strategy_name} — 逐月投入明细")
    print(f"{'=' * 60}")
    print(f"{'日期':14s} {'净值':>8s} {'投入金额':>10s} {'累计份额':>10s} {'累计投入':>10s} {'当前市值':>10s} {'收益率':>10s}")
    print("-" * 72)

    for _, row in invest_days.iterrows():
        invested = row["invested"]
        value = row["value"]
        ret = ((value - invested) / invested * 100) if invested > 0 else 0
        print(f"{row['date'].strftime('%Y-%m-%d'):14s} {row['nav']:>8.4f} "
              f"{row['amount']:>10.0f} {row['shares']:>10.2f} "
              f"{row['invested']:>10.0f} {row['value']:>10.0f} {ret:>+9.2f}%")


def show_fund(code, generate_chart=True, buy_fee=0.0, sell_fee=0.0):
    fund_list = search_fund(code)
    if len(fund_list) == 0:
        print(f"未找到基金: {code}")
        return
    fund = fund_list.iloc[0]
    print(f"\n{'=' * 60}")
    print(f"基金代码: {fund['code']}")
    print(f"基金名称: {fund['name']}")
    print(f"基金类型: {fund['fund_type']}")
    print(f"成立日期: {fund['estab_date']}")
    print(f"基金规模: {fund['规模(亿)']:.2f}亿")
    if buy_fee > 0 or sell_fee > 0:
        print(f"费率: 申购{buy_fee*100:.2f}% / 赎回{sell_fee*100:.2f}%")
    print(f"{'=' * 60}")

    result = run_all_strategies(code, buy_fee_rate=buy_fee, sell_fee_rate=sell_fee)
    if result is None:
        print("回测失败（数据不足或净值文件缺失）")
        return

    print_strategy_table(result)

    best_strat = result.loc[result["annualized_return_pct"].idxmax()]
    print_best_strategy_detail(code, result)
    print_investment_schedule(code, best_strat["strategy"])

    if generate_chart:
        viz.plot_strategy_curves(code, fund_name=fund["name"], save=True, show=False)
        print(f"\n图表已保存至: data/charts/")
        print(f"  策略曲线: {code}_strategies.png")

    ranking = db.get_ranking()
    if code in ranking["code"].values:
        rank = ranking[ranking["code"] == code].iloc[0]
        print(f"\n{'=' * 60}")
        print(f"全市场排名: 第{ranking[ranking['code'] == code].index[0] + 1}名 / 共{len(ranking)}只基金")
        print(f"最佳策略: {rank['strategy']}")
        print(f"综合评分: {rank['score']:.2f}")


def main():
    parser = argparse.ArgumentParser(description="基金定投深度分析")
    parser.add_argument("code", nargs="?", help="基金代码")
    parser.add_argument("--no-chart", action="store_true", help="跳过生成图表")
    parser.add_argument("--buy-fee", type=float, default=0.0, help="申购费率(如0.0015)")
    parser.add_argument("--sell-fee", type=float, default=0.0, help="赎回费率(如0.005)")
    args = parser.parse_args()

    if args.code:
        show_fund(args.code, generate_chart=not args.no_chart,
                  buy_fee=args.buy_fee, sell_fee=args.sell_fee)
        return

    fund_list = db.get_funds_df()
    ranking = db.get_ranking()
    ranking = ranking.merge(fund_list[["code", "name", "fund_type"]], on="code", how="left")
    top10 = ranking.head(10)

    print("=" * 60)
    print("基金定投分析系统")
    print("=" * 60)
    print("\n热门基金 Top10:")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        print(f"  {i}. {row['name']} ({row['code']}) - {row['strategy']} - 年化{row['annualized_return_pct']:+.1f}%")

    while True:
        try:
            inp = input(f"\n输入基金代码（或q退出）: ").strip()
            if inp.lower() in ("q", "quit", "exit"):
                break
            show_fund(inp, generate_chart=not args.no_chart)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")


if __name__ == "__main__":
    main()
