import pandas as pd

df = pd.read_csv("D:\\Project\\funding project\\data\\dca_ranking.csv", encoding="utf-8-sig")
print(f"总回测基金数: {len(df)}")
print()

print("Top 30 定投最优基金:")
print("=" * 120)
for i, (_, row) in enumerate(df.head(30).iterrows(), 1):
    print(f'{i:2d}. {row["name"]} ({row["code"]})')
    print(f'   类型:{row["fund_type"]}  规模:{row["规模(亿)"]:.1f}亿  策略:{row["strategy"]}')
    print(f'   年化:{row["annualized_return_pct"]:+7.2f}%  总收益:{row["total_return_pct"]:+7.2f}%  回撤:{row["max_drawdown_pct"]:6.2f}%')
    print(f'   夏普:{row["sharpe_ratio"]:.3f}  胜率:{row["win_rate_pct"]:5.1f}%  超一次性:{row["vs_lump_sum_pct"]:+7.2f}%  评分:{row["score"]:.2f}')
    print()

print("=" * 120)
print("\n策略分布统计:")
print(df["strategy"].value_counts().to_string())

print("\n\n各类型基金最优策略:")
for ft, sub in df.groupby("fund_type"):
    top = sub["strategy"].mode().iloc[0]
    avg_ret = sub["annualized_return_pct"].mean()
    avg_score = sub["score"].mean()
    print(f"  {ft}: 最优策略={top}, 平均年化={avg_ret:+.2f}%, 平均评分={avg_score:.2f}")
