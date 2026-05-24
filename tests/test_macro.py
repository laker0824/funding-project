import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from unittest.mock import patch, MagicMock
from macro import DIMENSIONS, FUND_TYPE_MACRO_MAP, get_macro_plan, build_queries, _guess_industry, format_macro_conclusion


def test_dimensions_count():
    assert len(DIMENSIONS) == 7


def test_dimension_labels():
    names = {d["label"] for d in DIMENSIONS.values()}
    assert "产业政策" in names
    assert "货币政策" in names
    assert "地缘政治" in names


def test_fund_type_mappings():
    assert len(FUND_TYPE_MACRO_MAP) == 16
    assert "QDII" in FUND_TYPE_MACRO_MAP
    assert "股票型" in FUND_TYPE_MACRO_MAP


def test_each_dimension_has_templates():
    for name, dim in DIMENSIONS.items():
        assert len(dim["templates"]) >= 2, f"{name} has <2 templates"
        assert len(dim["indicators"]) >= 1, f"{name} has no indicators"


def test_guess_industry_exact_match():
    assert _guess_industry("XX半导体产业混合", "股票型") == "半导体"


def test_guess_industry_partial_match():
    assert _guess_industry("XX智能混合", "股票型") == "人工智能"


def test_guess_industry_fallback_by_type():
    assert _guess_industry("XX全球机遇", "混合型") == "消费"


def test_guess_industry_fallback_default():
    assert _guess_industry("XX任意未知", "其他型") == "科技"


def test_guess_industry_qdii():
    assert _guess_industry("XX全球机遇", "QDII") == "海外"


def test_build_queries_returns_strings():
    queries = build_queries(["产业政策", "货币政策"], fund_name="招商白酒消费")
    assert isinstance(queries, list)
    assert len(queries) > 0
    assert all(isinstance(q, str) for q in queries)


def test_build_queries_max_8():
    queries = build_queries(list(DIMENSIONS.keys()), fund_name="XX科技")
    assert len(queries) <= 8


def test_build_queries_contains_keywords():
    queries = build_queries(["产业政策"], fund_name="半导体混合")
    assert any("半导体" in q for q in queries)


def test_build_queries_empty_dimensions():
    assert build_queries([], fund_name="XX") == []


def test_macro_plan_nonexistent_code():
    with patch("macro.db.get_fund_info", return_value=None):
        plan = get_macro_plan("999999")
        assert "error" in plan
        assert plan["dimensions"] == []


def test_macro_plan_returns_keys():
    fake_info = {"code": "000001", "name": "XX混合", "fund_type": "混合型", "estab_date": "2020-01-01", "scale": 10}
    with patch("macro.db.get_fund_info", return_value=fake_info):
        plan = get_macro_plan("000001")
        assert plan["code"] == "000001"
        assert plan["name"] == "XX混合"
        assert plan["fund_type"] == "混合型"
        assert isinstance(plan["dimensions"], list)
        assert isinstance(plan["search_queries"], list)


def test_macro_plan_dimensions_for_qdii():
    fake_info = {"code": "000002", "name": "XX全球机遇", "fund_type": "QDII-指数", "estab_date": "2020-01-01"}
    with patch("macro.db.get_fund_info", return_value=fake_info):
        plan = get_macro_plan("000002")
        assert "全球产业链" in plan["dimensions"]
        assert "汇率与资本" in plan["dimensions"]


def test_macro_plan_dimensions_for_stock():
    fake_info = {"code": "000003", "name": "XX价值精选", "fund_type": "股票型", "estab_date": "2020-01-01"}
    with patch("macro.db.get_fund_info", return_value=fake_info):
        plan = get_macro_plan("000003")
        assert "产业政策" in plan["dimensions"]
        assert "A股市场环境" in plan["dimensions"]


def test_format_macro_conclusion_empty():
    assert format_macro_conclusion({}) == ""


def test_format_macro_conclusion():
    result = format_macro_conclusion({
        "产业政策": {"key_signals": ["信号1", "信号2"]},
    })
    assert "产业政策" in result
    assert "信号1" in result


def test_all_templates_have_no_unmatched_brackets():
    for name, dim in DIMENSIONS.items():
        for tpl in dim["templates"]:
            open_count = tpl.count("{")
            close_count = tpl.count("}")
            assert open_count == close_count, f"{name} template bracket mismatch: {tpl}"


def test_fund_type_mappings_values_are_valid():
    valid = set(DIMENSIONS.keys())
    for ft, dims in FUND_TYPE_MACRO_MAP.items():
        for d in dims:
            assert d in valid, f"{ft} references unknown dimension '{d}'"
