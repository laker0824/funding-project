"""策略回测核心模块"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
NAV_DIR = os.path.join(DATA_DIR, "nav")


def load_nav(code):
    from db import load_nav as db_load_nav
    df = db_load_nav(code)
    if df is not None:
        return df
    path = os.path.join(NAV_DIR, f"{code}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ===================== 投资日期生成 =====================


def _next_biz_day(dates, target):
    """找到target当天或之后最近的交易日"""
    mask = dates >= target
    if not mask.any():
        return None
    return dates[mask].iloc[0]


def generate_schedule(nav_dates, start_date, end_date, freq="M", day=None, weekday=None):
    """生成投资日期表，自动对齐到实际交易日"""
    nav_dates = pd.Series(nav_dates).sort_values().reset_index(drop=True)
    mask = (nav_dates >= pd.Timestamp(start_date)) & (nav_dates <= pd.Timestamp(end_date))
    range_dates = nav_dates[mask]
    if len(range_dates) < 20:
        return pd.DataFrame(columns=["date"])

    targets = []
    if freq == "M":
        months = pd.date_range(start_date, end_date, freq="MS")
        for m in months:
            d = m.replace(day=min(day or 1, 28))
            nearest = _next_biz_day(nav_dates, d)
            if nearest is not None and nearest <= pd.Timestamp(end_date):
                targets.append(nearest)
    elif freq == "W":
        weeks = pd.date_range(start_date, end_date, freq="W-MON")
        for w in weeks:
            target = w + timedelta(days=(weekday or 0))
            nearest = _next_biz_day(nav_dates, target)
            if nearest is not None and nearest <= pd.Timestamp(end_date):
                targets.append(nearest)
    elif freq == "2W":
        biweeks = pd.date_range(start_date, end_date, freq="2W-MON")
        for w in biweeks:
            target = w + timedelta(days=(weekday or 0))
            nearest = _next_biz_day(nav_dates, target)
            if nearest is not None and nearest <= pd.Timestamp(end_date):
                targets.append(nearest)
    else:
        raise ValueError(f"Unsupported freq: {freq}")

    return pd.DataFrame({"date": sorted(set(targets))})


# ===================== 通用回测引擎 =====================


def run_backtest(nav_df, schedule, get_amount_fn, strategy_name="", buy_fee_rate=0.0, sell_fee_rate=0.0):
    """
    通用回测引擎
    nav_df: DataFrame with date, nav columns sorted by date
    schedule: DataFrame with date column (investment dates)
    get_amount_fn: function(date, nav_series, state) -> amount to invest
    buy_fee_rate: 申购费率 (e.g. 0.0015 for 0.15%)
    sell_fee_rate: 赎回费率 (e.g. 0.005 for 0.5%)
    returns: dict with metrics
    """
    nav_series = nav_df.set_index("date")["nav"]

    total_invested_with_fee = 0.0
    shares = 0.0
    peak_nav = nav_series.iloc[0]
    state = {"peak_nav": peak_nav, "total_invested": 0, "total_shares": 0, "resets": 0}

    rows = []
    for idx, row in nav_df.iterrows():
        d = row["date"]
        nav = row["nav"]
        is_invest_day = d in schedule["date"].values if len(schedule) > 0 else False

        amount = 0
        if is_invest_day:
            gross_amount = get_amount_fn(d, nav_series, state)
            if gross_amount > 0:
                net_amount = gross_amount * (1 - buy_fee_rate)
                fee = gross_amount - net_amount
                shares += net_amount / nav
                total_invested_with_fee += gross_amount
                state["total_invested"] = total_invested_with_fee
                state["total_shares"] = shares
                amount = gross_amount

        current_value = shares * nav

        if nav > state["peak_nav"]:
            state["peak_nav"] = nav

        rows.append({
            "date": d,
            "nav": nav,
            "amount": amount,
            "shares": shares,
            "invested": total_invested_with_fee,
            "value": current_value,
            "peak_nav": state["peak_nav"],
        })

    result_df = pd.DataFrame(rows)

    if sell_fee_rate > 0:
        final_value = result_df["value"].iloc[-1]
        sell_fee = final_value * sell_fee_rate
        last_idx = result_df.index[-1]
        result_df.loc[last_idx, "value"] = final_value - sell_fee
        result_df.loc[last_idx, "invested"] = total_invested_with_fee

    metrics = calc_metrics(result_df, nav_df, strategy_name)
    return metrics, result_df


# ===================== 策略实现 =====================


def strategy_regular(amount=1000):
    """定期定额: 固定金额"""
    def fn(date, nav_series, state):
        return amount
    return fn


def strategy_ma_deviation(base_amount=1000, ma_period=120, multiplier=2, max_mult=3):
    """均线偏离法: 价格低于均线多投，高于少投"""
    def fn(date, nav_series, state):
        idx = nav_series.index.get_loc(date)
        if idx < ma_period:
            return base_amount
        ma = nav_series.iloc[idx - ma_period + 1:idx + 1].mean()
        current = nav_series.iloc[idx]
        deviation = (ma - current) / ma
        ratio = 1 + multiplier * deviation
        ratio = max(0, min(ratio, max_mult))
        return base_amount * ratio
    return fn


def strategy_drawdown(base_amount=1000, threshold=0.1, add_ratio=1, max_mult=3):
    """回撤加仓法: 从高点回撤超过阈值时加码"""
    def fn(date, nav_series, state):
        idx = nav_series.index.get_loc(date)
        current = nav_series.iloc[idx]
        peak = state.get("running_peak", current)
        if current > peak:
            state["running_peak"] = current
            peak = current
        drawdown = (peak - current) / peak if peak > 0 else 0
        if drawdown > threshold:
            mult = 1 + add_ratio * (drawdown / threshold)
            mult = min(mult, max_mult)
            return base_amount * mult
        return base_amount
    return fn


def strategy_take_profit(amount=1000, profit_target=0.2):
    """止盈策略: 达目标收益时赎回并重新开始"""
    def fn(date, nav_series, state):
        invested = state.get("total_invested", 0)
        shares_held = state.get("total_shares", 0)
        current = nav_series.iloc[nav_series.index.get_loc(date)]
        current_value = shares_held * current

        if invested > 0 and current_value > invested * (1 + profit_target):
            # 止盈: 记录本次周期收益，重置
            state["total_invested"] = 0
            state["total_shares"] = 0
            state.setdefault("cycle_count", 0)
            state["cycle_count"] += 1
            return amount  # 重新开始定投
        return amount
    return fn


def strategy_ma_stop(base_amount=1000, ma_period=120, stop_deviation=0.15):
    """MA停投机制: NAV高于均线一定比例时停投"""
    def fn(date, nav_series, state):
        idx = nav_series.index.get_loc(date)
        if idx < ma_period:
            return base_amount
        ma = nav_series.iloc[idx - ma_period + 1:idx + 1].mean()
        current = nav_series.iloc[idx]
        if current > ma * (1 + stop_deviation):
            return 0
        return base_amount
    return fn


def strategy_value_average(base_amount=1000, target_growth=0.01):
    """价值平均法: 每月使总市值增加固定金额"""
    def fn(date, nav_series, state):
        idx = nav_series.index.get_loc(date)
        current = nav_series.iloc[idx]
        current_shares = state.get("total_shares", 0)
        current_value = current_shares * current
        target_value = state.get("month_count", 0) * base_amount * (1 + target_growth) ** state.get("month_count", 0)
        state["month_count"] = state.get("month_count", 0) + 1
        diff = target_value - current_value
        if diff > 0:
            return diff
        return 0
    return fn


# ===================== 指标计算 =====================


def calc_metrics(result_df, nav_df, strategy_name=""):
    """计算回测绩效指标"""
    invest_mask = result_df["invested"] > 0
    if not invest_mask.any():
        return {k: 0 for k in ["strategy", "total_invested", "final_value", "total_return_pct",
                                "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio",
                                "win_rate_pct", "calmar_ratio", "lump_sum_return_pct",
                                "vs_lump_sum_pct", "years", "invest_count"]}

    total_invested = result_df["invested"].iloc[-1]
    final_value = result_df["value"].iloc[-1]

    invest_rows = result_df[invest_mask]
    first_date = invest_rows["date"].iloc[0]
    last_date = result_df["date"].iloc[-1]
    years = max(0.5, (last_date - first_date).days / 365.25)

    total_return = (final_value - total_invested) / total_invested * 100 if total_invested > 0 else 0
    annualized = ((final_value / total_invested) ** (1 / years) - 1) * 100 if total_invested > 0 else 0

    first_invest_idx = invest_rows.index[0]
    values_post = result_df.loc[first_invest_idx:, "value"].values
    peak = np.maximum.accumulate(values_post)
    peak_safe = np.where(peak == 0, 1, peak)
    drawdowns = (peak_safe - values_post) / peak_safe * 100
    max_dd = drawdowns.max()

    invest_months = int((result_df["amount"] > 0).sum())
    win_months = 0
    for i in range(1, len(result_df)):
        if result_df["amount"].iloc[i] > 0:
            if result_df["value"].iloc[i] >= result_df["invested"].iloc[i]:
                win_months += 1
    win_rate = win_months / invest_months * 100 if invest_months > 0 else 0

    daily_returns = nav_df["nav"].pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        excess = daily_returns - 0.03 / 252
        sharpe = np.sqrt(252) * excess.mean() / excess.std()
    else:
        sharpe = 0

    lump_sum_return = (nav_df["nav"].iloc[-1] - nav_df["nav"].iloc[0]) / nav_df["nav"].iloc[0] * 100
    vs_lump_sum = total_return - lump_sum_return

    calmar = annualized / max_dd if max_dd > 0 else 0

    return {
        "strategy": strategy_name,
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(annualized, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate_pct": round(win_rate, 1),
        "calmar_ratio": round(calmar, 3),
        "lump_sum_return_pct": round(lump_sum_return, 2),
        "vs_lump_sum_pct": round(vs_lump_sum, 2),
        "years": round(years, 1),
        "invest_count": invest_months,
    }


# ===================== 策略调度 =====================


def run_all_strategies(code, start_date=None, end_date=None, years=None, buy_fee_rate=0.0, sell_fee_rate=0.0, min_period=200):
    """对一只基金运行所有策略"""
    nav_df = load_nav(code)
    if nav_df is None or len(nav_df) < 300:
        return None

    if start_date is None:
        if years is not None:
            start_date = nav_df["date"].max() - pd.DateOffset(years=years)
        else:
            start_date = nav_df["date"].max() - pd.DateOffset(years=3)
    if end_date is None:
        end_date = nav_df["date"].max()

    mask = (nav_df["date"] >= start_date) & (nav_df["date"] <= end_date)
    nav_period = nav_df[mask].copy().reset_index(drop=True)
    if len(nav_period) < min_period:
        return None

    strategies = []
    base_monthly = 1000

    kw = {"buy_fee_rate": buy_fee_rate, "sell_fee_rate": sell_fee_rate}

    # 1. 定期定额 (月)
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_regular(base_monthly), "定期定额(月)", **kw)
    strategies.append(m)

    # 2. 定期定额 (周)
    sched_w = generate_schedule(nav_period["date"], start_date, end_date, freq="W", weekday=0)
    m, r = run_backtest(nav_period, sched_w, strategy_regular(base_monthly / 4), "定期定额(周)", **kw)
    strategies.append(m)

    # 3. 均线偏离法
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_ma_deviation(base_monthly, ma_period=120), "均线偏离法", **kw)
    strategies.append(m)

    # 4. 回撤加仓法
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_drawdown(base_monthly, threshold=0.1), "回撤加仓法", **kw)
    strategies.append(m)

    # 5. 止盈策略
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_take_profit(base_monthly, profit_target=0.2), "止盈策略(20%)", **kw)
    strategies.append(m)

    # 6. MA停投机制
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_ma_stop(base_monthly, stop_deviation=0.15), "MA停投法", **kw)
    strategies.append(m)

    # 7. 价值平均法
    sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
    m, r = run_backtest(nav_period, sched, strategy_value_average(base_monthly), "价值平均法", **kw)
    strategies.append(m)

    result = pd.DataFrame(strategies)
    result.insert(0, "code", code)
    return result


def run_all_strategies_multi_window(code, windows=(1, 3, 5, 10), buy_fee_rate=0.0, sell_fee_rate=0.0):
    """对一只基金运行多个时间窗口的回测"""
    nav_df = load_nav(code)
    if nav_df is None or len(nav_df) < 300:
        return None

    end = nav_df["date"].max()
    all_results = []
    for y in windows:
        min_rows = max(100, y * 200)
        start = end - pd.DateOffset(years=y)
        mask = (nav_df["date"] >= start) & (nav_df["date"] <= end)
        if mask.sum() < min_rows:
            continue
        result = run_all_strategies(code, start_date=start, end_date=end, min_period=min_rows,
                                    buy_fee_rate=buy_fee_rate, sell_fee_rate=sell_fee_rate)
        if result is not None:
            result["window"] = f"{y}y"
            all_results.append(result)

    if not all_results:
        return None
    return pd.concat(all_results, ignore_index=True)


def composite_score(row, w_return=0.35, w_sharpe=0.25, w_calmar=0.2, w_winrate=0.1, w_vs_lump=0.1):
    """综合评分: 年化收益×0.35 + 夏普×0.25 + calmar×0.2 + 胜率×0.1 + 超一次性×0.1"""
    score = (
        row["annualized_return_pct"] * w_return
        + row["sharpe_ratio"] * 10 * w_sharpe
        + row["calmar_ratio"] * w_calmar
        + row["win_rate_pct"] * w_winrate
        + row["vs_lump_sum_pct"] * w_vs_lump
    )
    return round(score, 2)
