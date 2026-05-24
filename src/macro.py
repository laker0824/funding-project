"""宏观分析辅助模块 — 产业映射、搜索模板、基金-维度关联"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import db

# ── 7 大宏观维度 ──

DIMENSIONS = {
    "产业政策": {
        "label": "产业政策",
        "templates": [
            "十五五规划 {industry} 政策 {year}",
            "{industry} 产业政策 最新",
            "国家大基金 {industry} 投资",
        ],
        "indicators": ["政策力度(强/中/弱)", "财政补贴变化", "税收优惠"],
    },
    "货币政策": {
        "label": "货币政策",
        "templates": [
            "美联储 利率决议 {year}年{month}月",
            "中国央行 降准降息 LPR 最新",
            "MLF 操作 流动性 市场利率",
        ],
        "indicators": ["LPR", "MLF利率", "存款准备金率", "联邦基金利率"],
    },
    "地缘政治": {
        "label": "地缘政治",
        "templates": [
            "中美关系 最新 关税 {year}",
            "地缘冲突 金融市场 影响 最新",
            "科技出口管制 半导体 {year}",
        ],
        "indicators": ["风险偏好(高/中/低)", "避险资产走势"],
    },
    "A股市场环境": {
        "label": "A股市场环境",
        "templates": [
            "沪深300 走势 分析 {year}年{month}月",
            "A股 行业轮动 热点板块 {year}",
            "北向资金 A股 流向 最新",
        ],
        "indicators": ["沪深300", "成交量", "北向资金净流入"],
    },
    "行业监管": {
        "label": "行业监管",
        "templates": [
            "{industry} 监管政策 新规 最新",
            "证监会 {industry} 监管 2026",
            "行业整顿 {industry} 影响",
        ],
        "indicators": ["监管风险(高/中/低)"],
    },
    "汇率与资本": {
        "label": "汇率与资本",
        "templates": [
            "人民币汇率 美元 走势 {year}年{month}月",
            "外资 中国股市 债券 流动 {year}",
            "港股通 南向资金 最新",
        ],
        "indicators": ["USDCNY", "外资净买入", "资本流动方向"],
    },
    "全球产业链": {
        "label": "全球产业链",
        "templates": [
            "芯片法案 CHIPS Act 最新进展 {year}",
            "供应链转移 东南亚 墨西哥 {industry}",
            "中美贸易 关税 {industry} 最新",
        ],
        "indicators": ["产业链影响(正面/负面/中性)"],
    },
}

# ── 基金类型 → 宏观维度映射 ──

FUND_TYPE_MACRO_MAP = {
    "股票型":            ["产业政策", "A股市场环境", "货币政策", "行业监管"],
    "混合型-偏股":        ["产业政策", "A股市场环境", "货币政策"],
    "混合型-灵活":        ["产业政策", "A股市场环境", "行业监管", "地缘政治"],
    "混合型-平衡":        ["货币政策", "A股市场环境", "汇率与资本"],
    "混合型":            ["A股市场环境", "产业政策"],
    "指数型-股票":        ["A股市场环境", "货币政策", "产业政策"],
    "指数型-债券":        ["货币政策", "汇率与资本"],
    "指数型-海外股票":    ["全球产业链", "汇率与资本", "地缘政治", "货币政策"],
    "指数型":            ["A股市场环境", "货币政策"],
    "QDII-普通股票":     ["全球产业链", "汇率与资本", "地缘政治", "货币政策"],
    "QDII-混合偏股":     ["全球产业链", "汇率与资本", "地缘政治", "货币政策"],
    "QDII-混合平衡":     ["全球产业链", "汇率与资本"],
    "QDII-指数":         ["全球产业链", "汇率与资本", "地缘政治"],
    "QDII-商品":         ["地缘政治", "全球产业链", "汇率与资本"],
    "QDII-FOF":          ["全球产业链", "汇率与资本", "货币政策"],
    "QDII":              ["全球产业链", "汇率与资本", "地缘政治"],
}


def get_fund_type(code):
    """查基金类型"""
    info = db.get_fund_info(code)
    if info is None:
        return None
    return info.get("fund_type")


def get_macro_plan(code):
    """根据基金代码返回宏观分析计划"""
    info = db.get_fund_info(code)
    if info is None:
        return {"error": "基金不存在", "dimensions": []}

    fund_type = info.get("fund_type", "")
    fund_name = info.get("name", "")

    # 匹配维度（精确匹配 + 前缀匹配）
    dimensions = []
    for ft, dims in FUND_TYPE_MACRO_MAP.items():
        if ft.endswith("*"):
            if fund_type.startswith(ft[:-1]):
                dimensions = dims
                break
        elif ft == fund_type:
            dimensions = dims
            break
    else:
        dimensions = ["产业政策", "A股市场环境", "货币政策"]

    return {
        "code": code,
        "name": fund_name,
        "fund_type": fund_type,
        "dimensions": dimensions,
        "search_queries": build_queries(dimensions, fund_name, fund_type),
    }


def build_queries(dimensions, fund_name="", fund_type=""):
    """为指定维度生成搜索查询列表"""
    from datetime import datetime
    now = datetime.now()
    year = now.year
    month = now.month

    # 从基金名/类型推测产业关键词
    industry = _guess_industry(fund_name, fund_type)

    queries = []
    for dim_name in dimensions:
        dim = DIMENSIONS.get(dim_name)
        if dim is None:
            continue
        for tpl in dim["templates"]:
            q = tpl.format(industry=industry, year=year, month=month)
            queries.append(q)

    # 去重，最多返回 8 条
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:8]


def _guess_industry(fund_name, fund_type):
    """从基金名称推测关联产业"""
    # 常见产业关键词
    industry_keywords = {
        "半导体": ["半导体", "芯片", "集成电路", "电子"],
        "新能源": ["新能源", "光伏", "风电", "锂电池", "新能源车", "新能源汽车"],
        "人工智能": ["人工智能", "AI", "智能", "大数据", "云计算"],
        "生物医药": ["医药", "医疗", "生物", "健康", "医美"],
        "消费": ["消费", "白酒", "食品", "零售", "家电"],
        "金融": ["金融", "银行", "保险", "证券", "地产"],
        "军工": ["军工", "国防", "航空", "航天", "船舶"],
        "科技": ["科技", "创新", "成长", "信息", "通信", "5G"],
        "互联网": ["互联网", "互联", "平台", "软件", "传媒"],
        "周期": ["周期", "有色", "钢铁", "煤炭", "化工", "建材"],
        "港股": ["港股", "沪港深", "恒生", "H股", "中概"],
    }

    for industry, keywords in industry_keywords.items():
        for kw in keywords:
            if kw in fund_name:
                return industry

    # 按类型兜底
    type_defaults = {
        "QDII": "海外",
        "指数型-股票": "科技",
        "股票型": "科技",
        "混合型": "消费",
    }
    for ft, ind in type_defaults.items():
        if fund_type and ft in fund_type:
            return ind

    return "科技"


def format_macro_conclusion(dim_results):
    """将宏观搜索结论格式化为文本"""
    lines = []
    for dim_name, result in dim_results.items():
        if not result:
            continue
        lines.append(f"【{DIMENSIONS[dim_name]['label']}】")
        signals = result.get("key_signals", [])
        for s in signals[:3]:
            lines.append(f"  · {s}")
    return "\n".join(lines)
