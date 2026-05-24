"""一次性的 CSV → SQLite 迁移脚本"""
import pandas as pd
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from db import init_db, upsert_funds, save_ranking, save_detail, save_nav_batch, get_conn

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
NAV_DIR = os.path.join(DATA_DIR, "nav")


def _fix_code(df):
    df["code"] = df["code"].astype(str).str.strip().str.zfill(6)
    return df


def migrate_funds():
    print("迁移: funds 表...")
    path = os.path.join(DATA_DIR, "fund_list_filtered.csv")
    if not os.path.exists(path):
        print(f"  文件不存在: {path}")
        return 0
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    df = _fix_code(df)
    df = df.rename(columns={"规模(亿)": "scale"})
    upsert_funds(df)
    print(f"  完成: {len(df)} 条")
    return len(df)


def migrate_ranking():
    print("迁移: ranking 表...")
    path = os.path.join(DATA_DIR, "dca_ranking.csv")
    if not os.path.exists(path):
        print(f"  文件不存在: {path}")
        return 0
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    df = _fix_code(df)
    df = df.rename(columns={"规模(亿)": "scale"})
    save_ranking(df)
    print(f"  完成: {len(df)} 条")
    return len(df)


def migrate_detail():
    print("迁移: strategy_detail 表...")
    path = os.path.join(DATA_DIR, "dca_strategy_detail.csv")
    if not os.path.exists(path):
        print(f"  文件不存在: {path}")
        return 0
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    df = _fix_code(df)
    save_detail(df)
    print(f"  完成: {len(df)} 条")
    return len(df)


def migrate_one_nav(code):
    path = os.path.join(NAV_DIR, f"{code}.csv")
    if not os.path.exists(path):
        return code, 0
    try:
        df = pd.read_csv(path)
        rows = [(code, row["date"], row["nav"],
                 row.get("acc_nav") if pd.notna(row.get("acc_nav")) else None)
                for _, row in df.iterrows()]
        save_nav_batch(rows)
        return code, len(rows)
    except Exception as e:
        return code, -1


def migrate_nav(max_workers=8):
    print("迁移: nav 表...")
    if not os.path.exists(NAV_DIR):
        print(f"  目录不存在: {NAV_DIR}")
        return 0, 0

    codes = [f.replace(".csv", "") for f in os.listdir(NAV_DIR) if f.endswith(".csv")]
    total_rows = 0
    ok = 0
    fail = 0

    # 先检查哪些已有数据
    conn = get_conn()
    existing = set()
    try:
        for row in conn.execute("SELECT DISTINCT code FROM nav").fetchall():
            existing.add(row[0])
    except Exception:
        pass
    conn.close()

    codes = [c for c in codes if c not in existing]
    print(f"  总文件: {len(codes) + len(existing)}, 已有: {len(existing)}, 待导入: {len(codes)}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(migrate_one_nav, c): c for c in codes}
        for f in as_completed(futures):
            c, n = f.result()
            if n > 0:
                ok += 1
                total_rows += n
            elif n < 0:
                fail += 1
            if (ok + fail) % 200 == 0:
                elapsed = time.time() - t0
                print(f"    进度: {ok+fail}/{len(codes)}, 行数: {total_rows}, 耗时: {elapsed:.0f}s")

    print(f"  完成: 成功 {ok} 只, 失败 {fail} 只, 共 {total_rows} 行")
    return ok, fail


def main():
    print("=" * 50)
    print("CSV → SQLite 数据迁移")
    print("=" * 50)

    t0 = time.time()
    init_db()
    print(f"数据库初始化完成: {os.path.join(DATA_DIR, 'funding.db')}\n")

    n_funds = migrate_funds()
    n_rank = migrate_ranking()
    n_detail = migrate_detail()
    print()
    migrate_nav(max_workers=8)

    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed:.1f}s")
    print(f"  funds: {n_funds}")
    print(f"  ranking: {n_rank}")
    print(f"  detail: {n_detail}")


if __name__ == "__main__":
    main()
