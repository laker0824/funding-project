import pytest
import pandas as pd
import sqlite3
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import (
    get_conn, init_db, funds_exists, db_has_data,
    get_funds_df, get_fund_info, upsert_funds,
    load_nav, nav_count, save_nav_batch,
    get_ranking, save_ranking,
    get_detail, get_detail_by_code, save_detail,
    get_distinct_strategies,
)


class TestFunds:
    def test_upsert_and_get_funds(self):
        df = pd.DataFrame([
            {"code": "960033", "name": "测试基金", "fund_type": "股票型",
             "estab_date": "2020-01-01", "endnav_float": 3e8,
             "fund_company": "测试公司", "scale": 3.0},
        ])
        upsert_funds(df)
        funds = get_funds_df()
        assert len(funds) == 1
        assert funds.iloc[0]["code"] == "960033"

    def test_get_fund_info_returns_correct(self):
        df = pd.DataFrame([
            {"code": "960033", "name": "测试基金", "fund_type": "股票型",
             "estab_date": "2020-01-01", "endnav_float": 3e8,
             "fund_company": "测试公司", "scale": 3.0},
        ])
        upsert_funds(df)
        info = get_fund_info("960033")
        assert info is not None
        assert info["name"] == "测试基金"
        assert info["fund_type"] == "股票型"

    def test_get_fund_info_returns_none_for_unknown(self):
        assert get_fund_info("999999") is None

    def test_upsert_twice_replaces(self):
        df1 = pd.DataFrame([
            {"code": "960033", "name": "旧名字", "fund_type": "股票型",
             "estab_date": "2020-01-01", "endnav_float": 3e8,
             "fund_company": "测试公司", "scale": 3.0},
        ])
        upsert_funds(df1)
        df2 = pd.DataFrame([
            {"code": "960033", "name": "新名字", "fund_type": "混合型",
             "estab_date": "2020-01-01", "endnav_float": 5e8,
             "fund_company": "测试公司", "scale": 5.0},
        ])
        upsert_funds(df2)
        info = get_fund_info("960033")
        assert info["name"] == "新名字"

    def test_get_funds_returns_empty_on_error(self):
        assert isinstance(get_funds_df(), pd.DataFrame)


class TestNav:
    def test_save_and_load_nav(self):
        rows = [
            ("960033", "2023-01-01", 1.0, 1.0),
            ("960033", "2023-01-02", 1.1, 1.1),
            ("960033", "2023-01-03", 1.2, 1.2),
        ]
        save_nav_batch(rows)
        df = load_nav("960033")
        assert df is not None
        assert len(df) == 3

    def test_nav_count_returns_correct(self):
        rows = [
            ("960033", "2023-01-01", 1.0, 1.0),
            ("960033", "2023-01-02", 1.1, 1.1),
            ("960033", "2023-01-03", 1.2, 1.2),
        ]
        save_nav_batch(rows)
        count = nav_count("960033")
        assert count == 3

    def test_nav_count_returns_zero_for_unknown(self):
        assert nav_count("999999") == 0

    def test_save_nav_batch_replaces_existing(self):
        rows = [("960033", "2023-01-01", 2.0, 2.0)]
        save_nav_batch(rows)
        df = load_nav("960033")
        assert df is not None
        assert df.iloc[0]["nav"] == 2.0

    def test_load_nav_returns_none_for_empty(self):
        assert load_nav("999999") is None

    def test_load_nav_returns_none_for_none(self):
        assert load_nav(None) is None

    def test_save_empty_batch_does_nothing(self):
        save_nav_batch([])


class TestRanking:
    def test_save_and_get_ranking(self):
        df = pd.DataFrame([
            {"code": "960033", "window": "3y", "name": "测试",
             "fund_type": "股票型", "strategy": "价值平均法",
             "annualized_return_pct": 12.5, "max_drawdown_pct": -15.0,
             "sharpe_ratio": 0.8, "win_rate_pct": 65.0,
             "total_return_pct": 40.0, "vs_lump_sum_pct": 5.0, "score": 8.5},
        ])
        save_ranking(df)
        rank = get_ranking()
        assert len(rank) >= 1

    def test_get_ranking_filters_by_window(self):
        df = pd.DataFrame([
            {"code": "960033", "window": "1y", "name": "测试",
             "fund_type": "股票型", "strategy": "定期定额(月)",
             "annualized_return_pct": 5.0, "max_drawdown_pct": -10.0,
             "sharpe_ratio": 0.5, "win_rate_pct": 55.0,
             "total_return_pct": 5.0, "vs_lump_sum_pct": 2.0, "score": 6.0},
        ])
        save_ranking(df)
        rank_1y = get_ranking("1y")
        assert len(rank_1y) >= 1
        rank_3y = get_ranking("3y")
        assert len(rank_3y) == 0

    def test_save_empty_ranking_does_nothing(self):
        save_ranking(pd.DataFrame())


class TestDetail:
    def test_save_and_get_detail(self):
        df = pd.DataFrame([
            {"code": "960033", "window": "3y", "strategy": "定期定额(月)",
             "total_invested": 36000, "final_value": 45000,
             "total_return_pct": 25.0, "annualized_return_pct": 8.0,
             "max_drawdown_pct": -12.0, "sharpe_ratio": 0.6,
             "win_rate_pct": 60.0, "calmar_ratio": 0.67,
             "lump_sum_return_pct": 20.0, "vs_lump_sum_pct": 5.0,
             "years": 3.0, "invest_count": 36},
        ])
        save_detail(df)
        detail = get_detail()
        assert len(detail) >= 1

    def test_get_detail_filters_by_code_and_window(self):
        df = pd.DataFrame([
            {"code": "960033", "window": "3y", "strategy": "定期定额(月)",
             "total_invested": 36000, "final_value": 45000,
             "total_return_pct": 25.0, "annualized_return_pct": 8.0,
             "max_drawdown_pct": -12.0, "sharpe_ratio": 0.6,
             "win_rate_pct": 60.0, "calmar_ratio": 0.67,
             "lump_sum_return_pct": 20.0, "vs_lump_sum_pct": 5.0,
             "years": 3.0, "invest_count": 36},
        ])
        save_detail(df)
        det = get_detail_by_code("960033", "3y")
        assert len(det) >= 1
        assert det.iloc[0]["strategy"] == "定期定额(月)"

    def test_get_detail_returns_empty_for_unknown(self):
        assert len(get_detail_by_code("999999")) == 0

    def test_get_detail_returns_empty_for_none_code(self):
        assert len(get_detail_by_code(None)) == 0

    def test_save_empty_detail_does_nothing(self):
        save_detail(pd.DataFrame())

    def test_get_distinct_strategies(self):
        df = pd.DataFrame([
            {"code": "960033", "window": "3y", "strategy": "定期定额(月)",
             "total_invested": 36000, "final_value": 45000,
             "total_return_pct": 25.0, "annualized_return_pct": 8.0,
             "max_drawdown_pct": -12.0, "sharpe_ratio": 0.6,
             "win_rate_pct": 60.0, "calmar_ratio": 0.67,
             "lump_sum_return_pct": 20.0, "vs_lump_sum_pct": 5.0,
             "years": 3.0, "invest_count": 36},
        ])
        save_detail(df)
        strs = get_distinct_strategies()
        assert "定期定额(月)" in strs
