import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from strategies import (
    _next_biz_day, generate_schedule, run_backtest,
    strategy_regular, strategy_ma_deviation, strategy_drawdown,
    strategy_take_profit, strategy_ma_stop, strategy_value_average,
    calc_metrics, composite_score, _METRICS_DEFAULT,
)


@pytest.fixture
def nav_df():
    dates = pd.date_range("2020-01-01", "2023-12-31", freq="B")
    np.random.seed(42)
    nav = 100 * np.exp(np.random.randn(len(dates)).cumsum() * 0.01)
    return pd.DataFrame({"date": dates, "nav": nav})


@pytest.fixture
def simple_nav():
    dates = pd.date_range("2020-01-01", "2020-12-31", freq="B")
    nav = np.linspace(100, 110, len(dates))
    return pd.DataFrame({"date": dates, "nav": nav})


# ===================== _next_biz_day =====================

class TestNextBizDay:
    def test_finds_exact_match(self):
        dates = pd.date_range("2020-01-01", "2020-01-10", freq="B")
        assert _next_biz_day(dates, pd.Timestamp("2020-01-03")) == pd.Timestamp("2020-01-03")

    def test_finds_next_biz_day(self):
        dates = pd.date_range("2020-01-01", "2020-01-10", freq="B")
        result = _next_biz_day(dates, pd.Timestamp("2020-01-04"))
        assert result == pd.Timestamp("2020-01-06")

    def test_returns_none_for_empty(self):
        assert _next_biz_day(pd.Series([], dtype="datetime64[ns]"), pd.Timestamp("2020-01-01")) is None

    def test_returns_none_for_past_date(self):
        dates = pd.date_range("2020-01-05", "2020-01-10")
        assert _next_biz_day(dates, pd.Timestamp("2020-01-20")) is None

    def test_returns_none_for_none_input(self):
        assert _next_biz_day(None, pd.Timestamp("2020-01-01")) is None


# ===================== generate_schedule =====================

class TestGenerateSchedule:
    def test_monthly_schedule(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", "2020-12-31", freq="M", day=1)
        assert len(sched) == 12
        assert "date" in sched.columns

    def test_weekly_schedule(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", "2020-12-31", freq="W", weekday=0)
        assert len(sched) > 40

    def test_biweekly_schedule(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", "2020-12-31", freq="2W")
        assert len(sched) > 20

    def test_returns_empty_for_insufficient_data(self):
        dates = pd.date_range("2020-01-01", "2020-01-15", freq="B")
        sched = generate_schedule(dates, "2020-01-01", "2020-01-15", freq="M")
        assert len(sched) == 0

    def test_returns_empty_for_none_input(self):
        sched = generate_schedule(None, "2020-01-01", "2020-12-31")
        assert len(sched) == 0

    def test_raises_for_unknown_freq(self, nav_df):
        with pytest.raises(ValueError, match="Unsupported freq"):
            generate_schedule(nav_df["date"], "2020-01-01", "2020-12-31", freq="Y")

    def test_dates_are_sorted_and_unique(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", "2020-12-31", freq="M", day=1)
        dates = sched["date"].tolist()
        assert dates == sorted(set(dates))


# ===================== Strategy Functions =====================

class TestStrategyFunctions:
    def test_regular_returns_fixed_amount(self):
        fn = strategy_regular(amount=500)
        assert fn(None, None, {}) == 500

    def test_ma_deviation_returns_amount(self, nav_df):
        fn = strategy_ma_deviation(base_amount=1000, ma_period=20)
        nav_series = nav_df.set_index("date")["nav"]
        d = nav_df["date"].iloc[-1]
        amount = fn(d, nav_series, {})
        assert amount >= 0
        assert amount <= 3000

    def test_ma_deviation_uses_baseline_when_insufficient_data(self, nav_df):
        fn = strategy_ma_deviation(base_amount=1000, ma_period=200)
        nav_series = nav_df.set_index("date")["nav"]
        d = nav_df["date"].iloc[5]
        assert fn(d, nav_series, {}) == 1000

    def test_drawdown_base_amount(self, nav_df):
        fn = strategy_drawdown(base_amount=1000, threshold=0.1)
        nav_series = nav_df.set_index("date")["nav"]
        d = nav_df["date"].iloc[-1]
        amount = fn(d, nav_series, {"running_peak": nav_series.max()})
        assert amount >= 0

    def test_drawdown_returns_more_when_drawdown_exceeds_threshold(self):
        n = 260
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        nav = np.concatenate([np.linspace(100, 120, n // 2), np.linspace(120, 80, n // 2)])
        nav_series = pd.Series(nav, index=dates)
        fn = strategy_drawdown(base_amount=1000, threshold=0.1, add_ratio=1)
        d = dates[-1]
        state = {"running_peak": 120}
        amount = fn(d, nav_series, state)
        assert amount > 1000

    def test_take_profit_returns_normal_amount(self, nav_df):
        fn = strategy_take_profit(amount=1000, profit_target=0.2)
        nav_series = nav_df.set_index("date")["nav"]
        d = nav_df["date"].iloc[0]
        assert fn(d, nav_series, {"total_invested": 0, "total_shares": 0}) == 1000

    def test_ma_stop_returns_zero_when_above_threshold(self):
        n = 260
        flat_n = n - 100
        up_n = n - flat_n
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        nav = np.concatenate([np.linspace(100, 100, flat_n), np.linspace(100, 200, up_n)])
        nav_series = pd.Series(nav, index=dates)
        fn = strategy_ma_stop(base_amount=1000, ma_period=100, stop_deviation=0.05)
        d = dates[-1]
        assert fn(d, nav_series, {}) == 0

    def test_ma_stop_uses_baseline_when_insufficient_data(self, nav_df):
        fn = strategy_ma_stop(base_amount=1000, ma_period=1000)
        nav_series = nav_df.set_index("date")["nav"]
        d = nav_df["date"].iloc[5]
        assert fn(d, nav_series, {}) == 1000

    def test_value_average_first_call(self):
        fn = strategy_value_average(base_amount=1000, target_growth=0.01)
        state = {"total_shares": 0}
        dates = pd.date_range("2020-01-01", periods=3, freq="B")
        nav_series = pd.Series([100, 101, 102], index=dates)
        amount = fn(dates[0], nav_series, state)
        assert amount > 0
        assert state.get("month_count", 0) > 0


# ===================== run_backtest =====================

class TestRunBacktest:
    def test_returns_metrics_and_df(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", nav_df["date"].max(), freq="M")
        metrics, result_df = run_backtest(nav_df, sched, strategy_regular(1000), "定期定额")
        assert isinstance(metrics, dict)
        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) == len(nav_df)
        assert metrics["strategy"] == "定期定额"

    def test_returns_default_metrics_for_empty_nav(self):
        metrics, result_df = run_backtest(pd.DataFrame(), None, strategy_regular(1000), "empty")
        assert metrics["strategy"] == "empty"
        assert metrics["total_invested"] == 0

    def test_returns_default_metrics_for_none_nav(self):
        metrics, _ = run_backtest(None, None, strategy_regular(1000), "none")
        assert metrics["strategy"] == "none"

    def test_buy_fee_reduces_shares(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", nav_df["date"].max(), freq="M")
        metrics_no_fee, _ = run_backtest(nav_df, sched, strategy_regular(1000), "无费率")
        metrics_with_fee, _ = run_backtest(nav_df, sched, strategy_regular(1000), "有费率",
                                           buy_fee_rate=0.0015, sell_fee_rate=0.005)
        assert metrics_with_fee["total_return_pct"] < metrics_no_fee["total_return_pct"]

    def test_sell_fee_reduces_final_value(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", nav_df["date"].max(), freq="M")
        metrics_no, _ = run_backtest(nav_df, sched, strategy_regular(1000), "no_sell_fee")
        metrics_yes, _ = run_backtest(nav_df, sched, strategy_regular(1000), "sell_fee",
                                       sell_fee_rate=0.005)
        assert metrics_yes["final_value"] <= metrics_no["final_value"]

    def test_shares_increase_on_invest_days(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", nav_df["date"].max(), freq="M")
        _, result_df = run_backtest(nav_df, sched, strategy_regular(1000), "test")
        invest_rows = result_df[result_df["amount"] > 0]
        assert len(invest_rows) > 0
        for _, row in invest_rows.iterrows():
            assert row["shares"] > 0

    def test_backtest_with_no_schedule(self, nav_df):
        metrics, result_df = run_backtest(nav_df, pd.DataFrame(columns=["date"]),
                                          strategy_regular(1000), "无定投")
        assert metrics["invest_count"] == 0
        assert len(result_df) == len(nav_df)


# ===================== calc_metrics =====================

class TestCalcMetrics:
    def test_returns_default_for_empty_df(self):
        metrics = calc_metrics(pd.DataFrame(), None, "test")
        assert metrics["strategy"] == "test"
        assert metrics["total_invested"] == 0

    def test_computes_positive_return_for_rising_market(self, simple_nav):
        sched = generate_schedule(simple_nav["date"], "2020-01-01", "2020-12-31", freq="M")
        metrics, _ = run_backtest(simple_nav, sched, strategy_regular(1000), "上涨")
        assert metrics["total_return_pct"] > 0
        assert metrics["annualized_return_pct"] > 0

    def test_computes_years_correctly(self, simple_nav):
        sched = generate_schedule(simple_nav["date"], "2020-01-01", "2020-12-31", freq="M")
        metrics, _ = run_backtest(simple_nav, sched, strategy_regular(1000), "test")
        assert 0.5 <= metrics["years"] <= 2

    def test_sharpe_is_finite(self, nav_df):
        sched = generate_schedule(nav_df["date"], "2020-01-01", nav_df["date"].max(), freq="M")
        metrics, _ = run_backtest(nav_df, sched, strategy_regular(1000), "test")
        assert np.isfinite(metrics["sharpe_ratio"])


# ===================== composite_score =====================

class TestCompositeScore:
    def test_score_simple_case(self):
        row = {"annualized_return_pct": 10, "sharpe_ratio": 0.5,
               "calmar_ratio": 0.3, "win_rate_pct": 60, "vs_lump_sum_pct": 5}
        score = composite_score(row)
        assert score > 0

    def test_score_handles_nan(self):
        row = {"annualized_return_pct": float("nan"), "sharpe_ratio": None,
               "calmar_ratio": 0.3, "win_rate_pct": 60, "vs_lump_sum_pct": 5}
        score = composite_score(row)
        assert np.isfinite(score)

    def test_score_handles_missing_keys(self):
        row = {"annualized_return_pct": 10}
        score = composite_score(row)
        assert np.isfinite(score)

    def test_returns_zero_for_all_zeros(self):
        row = {"annualized_return_pct": 0, "sharpe_ratio": 0,
               "calmar_ratio": 0, "win_rate_pct": 0, "vs_lump_sum_pct": 0}
        assert composite_score(row) == 0.0

    def test_higher_values_give_higher_score(self):
        low = composite_score({"annualized_return_pct": 5, "sharpe_ratio": 0.3,
                               "calmar_ratio": 0.2, "win_rate_pct": 50, "vs_lump_sum_pct": 2})
        high = composite_score({"annualized_return_pct": 20, "sharpe_ratio": 1.0,
                                "calmar_ratio": 0.8, "win_rate_pct": 70, "vs_lump_sum_pct": 10})
        assert high > low
