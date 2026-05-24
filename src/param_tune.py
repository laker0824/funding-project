import pandas as pd
import numpy as np
import os
import sys
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools

sys.path.insert(0, os.path.dirname(__file__))
from strategies import load_nav, generate_schedule, run_backtest, composite_score
from strategies import strategy_regular, strategy_ma_deviation, strategy_drawdown
from strategies import strategy_take_profit, strategy_ma_stop, strategy_value_average

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUT_DIR = os.path.join(DATA_DIR, "param_tune")
os.makedirs(OUT_DIR, exist_ok=True)

BASE_AMOUNT = 1000

STRATEGY_PARAMS = {
    "均线偏离法": {
        "fn": strategy_ma_deviation,
        "grid": [
            {"ma_period": p, "multiplier": m, "max_mult": mx}
            for p in [60, 120, 200]
            for m in [1, 2, 3]
            for mx in [3, 5]
        ],
        "label": lambda kw: f"MA{kw['ma_period']}_M{kw['multiplier']}_max{kw['max_mult']}",
    },
    "回撤加仓法": {
        "fn": strategy_drawdown,
        "grid": [
            {"threshold": t, "add_ratio": a}
            for t in [0.05, 0.1, 0.15, 0.2]
            for a in [0.5, 1.0, 2.0]
        ],
        "label": lambda kw: f"DD{kw['threshold']}_AR{kw['add_ratio']}",
    },
    "止盈策略": {
        "fn": strategy_take_profit,
        "grid": [{"profit_target": p} for p in [0.1, 0.15, 0.2, 0.25, 0.3]],
        "label": lambda kw: f"TP{kw['profit_target']}",
    },
    "MA停投法": {
        "fn": strategy_ma_stop,
        "grid": [
            {"ma_period": p, "stop_deviation": s}
            for p in [60, 120, 200]
            for s in [0.1, 0.15, 0.2]
        ],
        "label": lambda kw: f"MA{kw['ma_period']}_SD{kw['stop_deviation']}",
    },
    "价值平均法": {
        "fn": strategy_value_average,
        "grid": [{"target_growth": g} for g in [0.005, 0.008, 0.01, 0.012, 0.015]],
        "label": lambda kw: f"TG{kw['target_growth']}",
    },
}


def run_param(code, strategy_name, param_kwargs):
    try:
        nav_df = load_nav(code)
        if nav_df is None or len(nav_df) < 300:
            return None

        start_date = nav_df["date"].max() - pd.DateOffset(years=3)
        end_date = nav_df["date"].max()
        mask = (nav_df["date"] >= start_date) & (nav_df["date"] <= end_date)
        nav_period = nav_df[mask].copy().reset_index(drop=True)
        if len(nav_period) < 250:
            return None

        sched = generate_schedule(nav_period["date"], start_date, end_date, freq="M", day=1)
        fn = STRATEGY_PARAMS[strategy_name]["fn"](BASE_AMOUNT, **param_kwargs)
        metrics, _ = run_backtest(nav_period, sched, fn, strategy_name)
        return metrics
    except Exception:
        return None


def tune_strategy(strategy_name, codes, max_workers=8):
    info = STRATEGY_PARAMS[strategy_name]
    results = []

    total_jobs = len(codes) * len(info["grid"])
    print(f"\n调优策略: {strategy_name}")
    print(f"  参数组合: {len(info['grid'])} 种")
    print(f"  基金样本: {len(codes)} 只")
    print(f"  总任务数: {total_jobs}")

    for params in info["grid"]:
        label = info["label"](params)
        scores = []
        n_success = 0
        rets = []
        dds = []
        sharpes = []

        for code in tqdm(codes, desc=f"  {label}"):
            m = run_param(code, strategy_name, params)
            if m is not None and m.get("annualized_return_pct", 0) != 0:
                score = composite_score(m)
                scores.append(score)
                rets.append(m["annualized_return_pct"])
                dds.append(m["max_drawdown_pct"])
                sharpes.append(m["sharpe_ratio"])
                n_success += 1

        if n_success > 0:
            results.append({
                "strategy": strategy_name,
                "params": str(params),
                **params,
                "n_funds": n_success,
                "avg_score": np.mean(scores),
                "avg_return": np.mean(rets),
                "avg_drawdown": np.mean(dds),
                "avg_sharpe": np.mean(sharpes),
                "median_score": np.median(scores),
                "p25_score": np.percentile(scores, 25),
                "p75_score": np.percentile(scores, 75),
            })

    df = pd.DataFrame(results)
    if len(df) > 0:
        df = df.sort_values("avg_score", ascending=False).reset_index(drop=True)
        path = os.path.join(OUT_DIR, f"{strategy_name}_param_tune.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n  最优参数组合 (按平均评分排序):")
        print(f"  {'排名':4s} {'参数':40s} {'平均评分':>10s} {'平均年化':>10s} {'平均回撤':>10s} {'平均夏普':>10s}")
        print(f"  {'-'*4} {'-'*40} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        for i, (_, row) in enumerate(df.iterrows()):
            print(f"  {i+1:4d} {row['params']:40s} {row['avg_score']:>10.2f} "
                  f"{row['avg_return']:>+9.2f}% {row['avg_drawdown']:>9.2f}% "
                  f"{row['avg_sharpe']:>9.3f}")
    return df


def tune_all(codes, strategies=None):
    if strategies is None:
        strategies = list(STRATEGY_PARAMS.keys())

    all_results = {}
    for sname in strategies:
        df = tune_strategy(sname, codes)
        all_results[sname] = df

    print(f"\n{'=' * 60}")
    print("参数调优总结 — 各策略最优参数")
    print(f"{'=' * 60}")
    for sname, df in all_results.items():
        if df is not None and len(df) > 0:
            best = df.iloc[0]
            print(f"\n{sname}:")
            print(f"  最优参数: {best['params']}")
            print(f"  平均评分: {best['avg_score']:.2f}")
            print(f"  平均年化: {best['avg_return']:+.2f}%")
            print(f"  平均回撤: {best['avg_drawdown']:.2f}%")

    return all_results


def main():
    import db
    ranking = db.get_ranking()
    n_sample = min(200, len(ranking))
    top_codes = ranking.head(n_sample)["code"].tolist()
    print(f"选取 Top {n_sample} 只基金进行参数调优")
    print(f"基金代码示例: {top_codes[:5]}")

    all_results = tune_all(top_codes)
    print("\n参数调优完成，结果已保存至 data/param_tune/")


if __name__ == "__main__":
    main()
