import sqlite3
import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "funding.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
    code TEXT PRIMARY KEY,
    name TEXT,
    fund_type TEXT,
    estab_date TEXT,
    endnav_float REAL,
    fund_company TEXT,
    scale REAL
);

CREATE TABLE IF NOT EXISTS nav (
    code TEXT,
    date TEXT,
    nav REAL,
    acc_nav REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_nav_code ON nav(code);

CREATE TABLE IF NOT EXISTS ranking (
    code TEXT,
    window TEXT DEFAULT '3y',
    name TEXT,
    fund_type TEXT,
    scale REAL,
    strategy TEXT,
    annualized_return_pct REAL,
    max_drawdown_pct REAL,
    sharpe_ratio REAL,
    win_rate_pct REAL,
    total_return_pct REAL,
    vs_lump_sum_pct REAL,
    score REAL,
    PRIMARY KEY (code, window)
);

CREATE TABLE IF NOT EXISTS strategy_detail (
    code TEXT,
    window TEXT DEFAULT '3y',
    strategy TEXT,
    total_invested REAL,
    final_value REAL,
    total_return_pct REAL,
    annualized_return_pct REAL,
    max_drawdown_pct REAL,
    sharpe_ratio REAL,
    win_rate_pct REAL,
    calmar_ratio REAL,
    lump_sum_return_pct REAL,
    vs_lump_sum_pct REAL,
    years REAL,
    invest_count INTEGER,
    PRIMARY KEY (code, strategy, window)
);
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def funds_exists():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) FROM funds").fetchone()
    conn.close()
    return row[0] > 0


def db_has_data():
    conn = get_conn()
    try:
        rc = conn.execute("SELECT COUNT(*) FROM ranking").fetchone()[0]
        nc = conn.execute("SELECT COUNT(*) FROM nav LIMIT 1").fetchone()[0]
        conn.close()
        return rc > 0 and nc > 0
    except Exception:
        conn.close()
        return False


# ── funds ──

def get_funds_df():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM funds", conn, dtype={"code": str})
    conn.close()
    return df


def get_fund_info(code):
    conn = get_conn()
    row = conn.execute("SELECT * FROM funds WHERE code = ?", (code,)).fetchone()
    conn.close()
    if row is None:
        return None
    cols = ["code", "name", "fund_type", "estab_date", "endnav_float", "fund_company", "scale"]
    return dict(zip(cols, row))


def upsert_funds(df):
    conn = get_conn()
    df.to_sql("funds", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


# ── nav ──

def load_nav(code):
    conn = get_conn()
    df = pd.read_sql(
        "SELECT date, nav, acc_nav FROM nav WHERE code = ? ORDER BY date",
        conn, params=(code,)
    )
    conn.close()
    if len(df) == 0:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df


def nav_count(code):
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) FROM nav WHERE code = ?", (code,)).fetchone()
    conn.close()
    return row[0]


def save_nav_batch(rows):
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM nav LIMIT 1")
    except Exception:
        init_db()
        conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO nav (code, date, nav, acc_nav) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()
    conn.close()


# ── ranking ──

def get_ranking(window=None):
    conn = get_conn()
    if window:
        df = pd.read_sql("SELECT * FROM ranking WHERE window = ?", conn,
                         params=(window,), dtype={"code": str})
    else:
        df = pd.read_sql("SELECT * FROM ranking", conn, dtype={"code": str})
    conn.close()
    return df


def save_ranking(df):
    conn = get_conn()
    df.to_sql("ranking", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


# ── strategy_detail ──

def get_detail(window=None):
    conn = get_conn()
    if window:
        df = pd.read_sql("SELECT * FROM strategy_detail WHERE window = ?", conn,
                         params=(window,), dtype={"code": str})
    else:
        df = pd.read_sql("SELECT * FROM strategy_detail", conn, dtype={"code": str})
    conn.close()
    return df


def get_detail_by_code(code, window=None):
    conn = get_conn()
    if window:
        df = pd.read_sql(
            "SELECT * FROM strategy_detail WHERE code = ? AND window = ?", conn,
            params=(code, window), dtype={"code": str}
        )
    else:
        df = pd.read_sql(
            "SELECT * FROM strategy_detail WHERE code = ?", conn,
            params=(code,), dtype={"code": str}
        )
    conn.close()
    return df


def save_detail(df):
    conn = get_conn()
    df.to_sql("strategy_detail", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


def get_distinct_strategies():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT strategy FROM strategy_detail").fetchall()
    conn.close()
    return [r[0] for r in rows]
