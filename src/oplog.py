import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "operations.log")


def _ensure():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("time\ttype\tduration_s\tdetail\n")


def _append(type_, duration_s, detail):
    _ensure()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts}\t{type_}\t{duration_s:.0f}\t{detail}\n")


def log_download(funds_total, ok, fail, duration_s):
    detail = f"funds={funds_total} ok={ok} fail={fail}"
    _append("DOWNLOAD", duration_s, detail)


def log_backtest(windows, funds_count, duration_s, summary=None):
    detail = f"windows={windows} funds={funds_count}"
    if summary:
        detail += f" {summary}"
    _append("BACKTEST", duration_s, detail)


def show():
    if not os.path.exists(LOG_FILE):
        print("暂无操作记录")
        return
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        print(f.read())
