import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import logging
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import oplog

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

logger = logging.getLogger("downloader")
if not logger.handlers:
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_sh)
    logger.setLevel(logging.INFO)

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
    url = "https://fund.eastmoney.com/js/fundcode_search.js"
    resp = requests.get(url, timeout=15)
    data = json.loads(resp.text[resp.text.index("[") : -1])
    df = pd.DataFrame(data, columns=["code", "pinyin", "name", "fund_type", "pinyin_full"])
    df = df.drop(columns=["pinyin", "pinyin_full"])
    df["code"] = df["code"].str.strip()
    logger.info("全市场基金总数: %d", len(df))
    return df


def fetch_fund_info_single(code):
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
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_fund_info_single, code): code for code in codes}
        done_count = 0
        total = len(codes)
        for f in as_completed(futures):
            results.append(f.result())
            done_count += 1
            if done_count % 200 == 0 or done_count == total:
                logger.info("获取基金信息: %d/%d", done_count, total)
    return pd.DataFrame(results)


def fetch_nav_single(code):
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
                try:
                    nav_f = float(nav)
                except (ValueError, TypeError):
                    continue
                try:
                    acc_nav_f = float(acc_nav) if acc_nav and acc_nav not in ("", "--", "N/A") else None
                except (ValueError, TypeError):
                    acc_nav_f = None
                rows.append({
                    "date": r["FSRQ"],
                    "nav": nav_f,
                    "acc_nav": acc_nav_f,
                })
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                return df.sort_values("date").reset_index(drop=True)
        except Exception:
            time.sleep(1)
    return None


def download_nav_parallel(codes, max_workers=5):
    nav_dir = os.path.join(DATA_DIR, "nav")
    os.makedirs(nav_dir, exist_ok=True)

    existing = {f.replace(".csv", "") for f in os.listdir(nav_dir) if f.endswith(".csv")}
    codes = [c for c in codes if c not in existing]
    logger.info("已存在 %d 只, 还需下载 %d 只", len(existing), len(codes))

    success = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_nav_single, code): code for code in codes}
        done_count = 0
        total = len(futures)
        for f in as_completed(futures):
            code = futures[f]
            done_count += 1
            try:
                df = f.result()
                if df is not None and len(df) > 50:
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
            if done_count % 100 == 0 or done_count == total:
                logger.info("下载净值: %d/%d只 (成功%d)", done_count, total, success)
    return success, len(codes) - success



def download_index_data(codes=None):
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
            logger.warning("%s: 未知代码", code)
            continue
        symbol, name = symbol_map[code]
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            rows = [(code, str(row["date"])[:10], float(row["close"]))
                    for _, row in df.iterrows()]
            save_index_data(code, rows)
            logger.info("%s (%s): %d 条", name, code, len(rows))
        except Exception as e:
            logger.warning("%s (%s) 下载失败: %s", name, code, e)

if __name__ == "__main__":
    _t0 = time.time()
    logger.info("=" * 50)
    logger.info("步骤1: 获取全市场基金列表")
    fund_list = get_fund_list()

    logger.info("步骤2: 筛选目标类型")
    target = fund_list[fund_list["fund_type"].isin(TARGET_TYPES)].copy()
    logger.info("目标类型基金: %d", len(target))
    for t, cnt in target["fund_type"].value_counts().items():
        logger.info("  %s: %d", t, cnt)

    logger.info("步骤3: 并行获取基金详细信息")
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

    logger.info("步骤4: 筛选结果（成立>1年, 规模>2亿）")
    logger.info("  符合条件: %d", len(filtered))

    summary = filtered[["code", "name", "fund_type", "estab_date", "endnav_float", "fund_company"]].copy()
    summary["endnav_yi"] = (summary["endnav_float"] / 1e8).round(2)
    summary = summary.rename(columns={"endnav_yi": "规模(亿)"})
    summary.to_csv(os.path.join(DATA_DIR, "fund_list_filtered.csv"), index=False, encoding="utf-8-sig")
    logger.info("  已保存: data/fund_list_filtered.csv")

    logger.info("步骤4b: 更新数据库基金列表")
    try:
        from db import init_db, upsert_funds, save_nav_batch
        init_db()
        fund_db = summary[["code", "name", "fund_type", "estab_date", "endnav_float", "fund_company",
                           "规模(亿)"]].copy()
        fund_db = fund_db.rename(columns={"规模(亿)": "scale"})
        fund_db["code"] = fund_db["code"].astype(str).str.strip()
        upsert_funds(fund_db)
        logger.info("  数据库已更新: %d 只基金", len(fund_db))
    except Exception as e:
        logger.warning("  数据库更新失败: %s", e)

    logger.info("步骤5: 并行下载历史净值数据")
    from db import init_db
    init_db()
    qualified = filtered["code"].tolist()
    logger.info("  需下载: %d 只", len(qualified))
    ok, fail = download_nav_parallel(qualified, max_workers=8)
    logger.info("完成: 成功 %d, 失败 %d", ok, fail)

    logger.info("步骤6: 下载基准指数数据")
    download_index_data()
    logger.info("  基准指数下载完成")

    _dur = time.time() - _t0
    oplog.log_download(funds_total=len(filtered), ok=ok, fail=fail, duration_s=_dur)
    logger.info("操作已记录到日志")
