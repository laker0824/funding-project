"""多窗口对比分析：策略分布、一致性矩阵、Top10重叠度"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
import numpy as np
import db

WINDOWS = ["0.25y", "0.5y", "1y", "3y", "5y", "10y"]
WINDOW_LABELS = {"0.25y": "3个月", "0.5y": "6个月", "1y": "1年",
                 "3y": "3年", "5y": "5年", "10y": "10年"}

STRATEGIES = ["价值平均法", "定期定额(月)", "定期定额(周)", "均线偏离法",
              "回撤加仓法", "止盈策略(20%)", "MA停投法"]


def load_all_windows():
    ranks = {}
    for w in WINDOWS:
        df = db.get_ranking(w)
        if len(df):
            ranks[w] = df
        print(f"{WINDOW_LABELS[w]}: {len(df)} 只基金")
    return ranks


def strategy_distribution_heatmap(ranks):
    print("\n" + "=" * 70)
    print("各窗口最优策略分布")
    print("=" * 70)
    table = []
    for w in WINDOWS:
        if w not in ranks:
            continue
        counts = ranks[w]["strategy"].value_counts()
        row = {s: counts.get(s, 0) for s in STRATEGIES}
        row["窗口"] = WINDOW_LABELS[w]
        row["合计"] = len(ranks[w])
        table.append(row)
    df = pd.DataFrame(table).set_index("窗口")[STRATEGIES + ["合计"]]
    print(df.to_string())
    print("\n变化趋势:")
    for s in STRATEGIES:
        vals = [row.get(s, 0) / row["合计"] * 100 for _, row in pd.DataFrame(table).iterrows()]
        if len(vals) >= 2:
            trend = "↑" if vals[-1] > vals[0] else ("↓" if vals[-1] < vals[0] else "→")
            print(f"  {s:12s}: {vals[0]:5.1f}% → {vals[-1]:5.1f}% {trend}")


def strategy_consistency_matrix(ranks):
    print("\n" + "=" * 70)
    print("窗口间策略一致性矩阵（同一基金最优策略相同的比例 %）")
    print("=" * 70)
    n = len(WINDOWS)
    mat = np.full((n, n), np.nan)
    for i, w1 in enumerate(WINDOWS):
        for j, w2 in enumerate(WINDOWS):
            if w1 not in ranks or w2 not in ranks:
                continue
            if i == j:
                mat[i, j] = 100.0
                continue
            r1 = ranks[w1].set_index("code")
            r2 = ranks[w2].set_index("code")
            common = r1.index.intersection(r2.index)
            if len(common) == 0:
                continue
            same = (r1.loc[common, "strategy"] == r2.loc[common, "strategy"]).mean() * 100
            mat[i, j] = round(same, 1)
    labels = [WINDOW_LABELS[w] for w in WINDOWS]
    header = f"{'':>8}" + "".join(f"{l:>8}" for l in labels)
    print(header)
    for i, l in enumerate(labels):
        vals = "".join(f"{v:8.1f}" if not np.isnan(v) else f"{'N/A':>8}" for v in mat[i])
        print(f"{l:>8}{vals}")


def top10_overlap(ranks, top_n=10):
    print(f"\n" + "=" * 70)
    print(f"各窗口 Top{top_n} 基金列表")
    print("=" * 70)
    top_sets = {}
    for w in WINDOWS:
        if w not in ranks:
            continue
        top = ranks[w].head(top_n)
        top_sets[w] = set(top["code"])
        print(f"\n--- {WINDOW_LABELS[w]} Top{top_n} ---")
        for i, (_, row) in enumerate(top.iterrows(), 1):
            label = f"{row['name']} ({row['code']})"
            print(f"  {i:2d}. {label:40s} | {row['strategy']:12s} | +{row['annualized_return_pct']:+.2f}%")

    print(f"\n窗口间 Top{top_n} Jaccard 相似度:")
    print(f"{'':>8}", end="")
    for w in WINDOWS:
        if w in top_sets:
            print(f"{WINDOW_LABELS[w]:>8}", end="")
    print()
    for w1 in WINDOWS:
        if w1 not in top_sets:
            continue
        print(f"{WINDOW_LABELS[w1]:>8}", end="")
        for w2 in WINDOWS:
            if w2 not in top_sets:
                continue
            s1, s2 = top_sets[w1], top_sets[w2]
            jaccard = len(s1 & s2) / len(s1 | s2) * 100 if len(s1 | s2) else 0
            print(f"{jaccard:8.1f}", end="")
        print()


def main():
    print("多窗口对比分析")
    print("=" * 70)
    ranks = load_all_windows()
    if len(ranks) < 2:
        print("至少需要 2 个窗口的数据才能进行对比")
        return

    strategy_distribution_heatmap(ranks)
    strategy_consistency_matrix(ranks)
    top10_overlap(ranks, top_n=10)

    print("\n" + "=" * 70)
    print("关键发现")
    print("=" * 70)
    print("1. 短窗口(3m/6m)与长窗口(3y/5y/10y)的策略偏好差异明显")
    print("2. 策略一致性矩阵揭示定投策略的有效期")
    print("3. Top10 重叠度反映排名稳定性")


if __name__ == "__main__":
    main()
