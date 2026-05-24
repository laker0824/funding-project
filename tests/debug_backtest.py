import os, sys, random, pandas as pd
sys.path.insert(0, "D:\\Project\\funding project\\src")
from strategies import run_all_strategies

test_codes = ["000001", "110011", "510300", "159919", "512170", "960033"]
for c in test_codes:
    res = run_all_strategies(c)
    status = "OK" if res is not None else "FAIL"
    rows = len(res) if res is not None else 0
    print(f"{c}: {status}, strategies={rows}")

# Also check some random failed funds
funds = pd.read_csv("D:\\Project\\funding project\\data\\fund_list_filtered.csv", encoding="utf-8-sig")
codes = funds["code"].tolist()
random.seed(42)
sample = random.sample(codes, min(10, len(codes)))
print("\nRandom 10 funds:")
for c in sample:
    res = run_all_strategies(c)
    status = "OK" if res is not None else "FAIL"
    print(f"  {c}: {status}")
