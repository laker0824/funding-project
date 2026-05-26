import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from tqdm import tqdm
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import oplog

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
    "Referer": "https://m.eastmoney.com/",
}

NAV_PARAMS = {
    "IsShareNet": "true",
    "MobileKey": "1",
    "appType": "ttjj",
    "appVersion": "6.2.8",
    "cToken": "1",
    "deviceid": "1",
    "pageSize": "40000",
    "plat": "Iphone",
    "product": "EFund",
    "serverVersion": "6.2.8",
    "uToken": "1",
    "userId": "1",
    "version": "6.2.8",
}

TARGET_TYPES = {
    "股票型", "混合型-偏股", "混合型-灵活", "混合型-平衡",
    "指数型-股票", "指数型-海外股票", "指数型-其他",
    "QDII-普通股票", "QDII-混合偏股", "QDII-混合灵活", "QDII-混合平衡",
    "QDII-FOF", "QDII-商品", "QDII-REITs",
}


def get_fund_list():
    """获取全市场基金列表（含类型）"""
    url = "https://fund.eastmoney.com/js/fundcode_search.js"
    resp = requests.get(url, timeout=15)
    data = json.loads(resp.text[resp.text.index("[") : -1])
    df = pd.DataFrame(data, columns=["code", "pinyin", "name", "fund_type", "pinyin_full"])
    df = df.drop(columns=["pinyin", "pinyin_full"])
    df["code"] = df["code"].str.strip()
    print(f"全市场基金总数: {len(df)}")
    return df


def fetch_fund_info_single(code):
    """获取单只基金详细信息"""
    url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNNBasicInformation"
    params = {
        "FCODE": code,
        "deviceid": "3EA024C2-7F22-408B-95E4-383D38160FB3",
        "plat": "Iphone",
        "product": "EFund",
        "version": "6.3.8",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        raw = resp.json().get("Datas", {})
        return {
            "code": code,
            "ftype": raw.get("FTYPE", ""),
            "estab_date": raw.get("ESTABDATE", ""),
            "endnav": float(raw.get("ENDNAV", 0) or 0),
            "fund_company": raw.get("JJGS", ""),
        }
    except Exception:
        return {"code": code, "ftype": "", "estab_date": "", "endnav": 0, "fund_company": ""}


def get_fund_info_parallel(codes, max_workers=10):
    """并行获取基金基本信息"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_fund_info_single, code): code for code in codes}
        for f in tqdm(as_completed(futures), total=len(codes), desc="获取基金信息"):
            results.append(f.result())
    return pd.DataFrame(results)


def fetch_nav_single(code):
    """获取单只基金历史净值"""
    url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHisNetList"
    params = {"FCODE": code, "pageIndex": "1", **NAV_PARAMS}
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        "Referer": "https://m.eastmoney.com/",
    }
    for _ in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            records = resp.json().get("Datas", [])
            rows = []
            for r in records:
                nav = r.get("DWJZ", "")
                acc_nav = r.get("LJJZ", "")
                if not nav:
                    continue
                rows.append({
                    "date": r["FSRQ"],
                    "nav": float(nav),
                    "acc_nav": float(acc_nav) if acc_nav and acc_nav != "" else None,
                })
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                return df.sort_values("date").reset_index(drop=True)
        except Exception:
            time.sleep(1)
    return None


def download_nav_parallel(codes, max_workers=5):
    """并行下载基金净值数据"""
    nav_dir = os.path.join(DATA_DIR, "nav")
    os.makedirs(nav_dir, exist_ok=True)

    existing = {f.replace(".csv", "") for f in os.listdir(nav_dir) if f.endswith(".csv")}
    codes = [c for c in codes if c not in existing]
    print(f"已存在 {len(existing)} 只, 还需下载 {len(codes)} 只")

    success = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_nav_single, code): code for code in codes}
        for f in tqdm(as_completed(futures), total=len(futures), desc="下载净值"):
            code = futures[f]
            try:
                df = f.result()
                if df is not None and len(df) > 250:
                    df.to_csv(os.path.join(nav_dir, f"{code}.csv"), index=False, encoding="utf-8-sig")
                    try:
                        from db import save_nav_batch
                        rows = [(code, r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else r["date"],
                                 r["nav"], r.get("acc_nav") if pd.notna(r.get("acc_nav")) else None)
                                for _, r in df.iterrows()]
                        save_nav_batch(rows)
                    except Exception:
                        pass
                    success += 1
            except Exception:
                pass
    return success, len(codes) - success


if __name__ == "__main__":
    _t0 = time.time()
    print("=" * 50)
    print("步骤1: 获取全市场基金列表")
    fund_list = get_fund_list()

    print("\n步骤2: 筛选目标类型")
    target = fund_list[fund_list["fund_type"].isin(TARGET_TYPES)].copy()
    print(f"目标类型基金: {len(target)}")
    for t, cnt in target["fund_type"].value_counts().items():
        print(f"  {t}: {cnt}")

    print("\n步骤3: 并行获取基金详细信息")
    info_df = get_fund_info_parallel(target["code"].tolist(), max_workers=15)
    fund_full = target.merge(info_df, on="code", how="left")

    cutoff_date = (datetime.now() - timedelta(days=365 * 1)).strftime("%Y-%m-%d")
    fund_full["estab_date_parsed"] = pd.to_datetime(fund_full["estab_date"], errors="coerce")
    fund_full["endnav_float"] = pd.to_numeric(fund_full["endnav"], errors="coerce")

    mask = (
        fund_full["estab_date_parsed"].notna()
        & (fund_full["estab_date_parsed"] < cutoff_date)
        & (fund_full["endnav_float"] >= 2e8)
    )
    filtered = fund_full[mask].copy()
    filtered = filtered.sort_values("endnav_float", ascending=False)

    print(f"\n步骤4: 筛选结果（成立>1年, 规模>2亿）")
    print(f"  符合条件: {len(filtered)}")

    summary = filtered[["code", "name", "fund_type", "estab_date", "endnav_float", "fund_company"]].copy()
    summary["endnav_yi"] = (summary["endnav_float"] / 1e8).round(2)
    summary = summary.rename(columns={"endnav_yi": "规模(亿)"})
    summary.to_csv(os.path.join(DATA_DIR, "fund_list_filtered.csv"), index=False, encoding="utf-8-sig")
    print(f"  已保存: data/fund_list_filtered.csv")

    print("\n步骤4b: 更新数据库基金列表")
    try:
        from db import init_db, upsert_funds, save_nav_batch
        init_db()
        fund_db = summary[["code", "name", "fund_type", "estab_date", "endnav_float", "fund_company",
                           "规模(亿)"]].copy()
        fund_db = fund_db.rename(columns={"规模(亿)": "scale"})
        fund_db["code"] = fund_db["code"].astype(str).str.strip()
        upsert_funds(fund_db)
        print(f"  数据库已更新: {len(fund_db)} 只基金")
    except Exception as e:
        print(f"  数据库更新失败: {e}")

    print("\n步骤5: 并行下载历史净值数据")
    from db import init_db
    init_db()
    qualified = filtered["code"].tolist()
    print(f"  需下载: {len(qualified)} 只")
    ok, fail = download_nav_parallel(qualified, max_workers=8)
    print(f"\n完成: 成功 {ok}, 失败 {fail}")

    print("\n步骤6: 下载基准指数数据")
    download_index_data()
    print("  基准指数下载完成")

    _dur = time.time() - _t0
    oplog.log_download(funds_total=len(filtered), ok=ok, fail=fail, duration_s=_dur)
    print(f"\n操作已记录到日志")


def download_index_data(codes=None):
    """下载沪深300/中证500等指数日线数据（使用 AKShare）"""
    from db import INDEX_CODES, save_index_data
    import akshare as ak

    if codes is None:
        codes = list(INDEX_CODES.keys())

    symbol_map = {
        "000300": ("sh000300", "沪深300"),
        "000905": ("sh000905", "中证500"),
        "000688": ("sh000688", "科创50"),
        "399001": ("sz399001", "深证成指"),
    }

    for code in codes:
        if code not in symbol_map:
            print(f"  {code}: 未知代码")
            continue
        symbol, name = symbol_map[code]
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            rows = [(code, str(row["date"])[:10], float(row["close"]))
                    for _, row in df.iterrows()]
            save_index_data(code, rows)
            print(f"  {name} ({code}): {len(rows)} 条")
        except Exception as e:
            print(f"  {name} ({code}) 下载失败: {e}")
