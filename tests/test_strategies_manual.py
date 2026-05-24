import sys
sys.path.insert(0, "D:\\Project\\funding project\\src")
from strategies import run_all_strategies

for code in ["110011", "510300", "000001"]:
    result = run_all_strategies(code)
    if result is not None:
        print(f"\n=== {code} ===")
        for _, row in result.iterrows():
            print(f"  {row['strategy']:16s} | 年化:{row['annualized_return_pct']:+7.2f}% | 回撤:{row['max_drawdown_pct']:6.2f}% | 夏普:{row['sharpe_ratio']:.3f} | 胜率:{row['win_rate_pct']:5.1f}%")
