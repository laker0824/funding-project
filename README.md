# 基金定投策略回测分析系统

基于中国市场公募基金历史净值数据，对 **7 种定投策略** 进行 **6 个时间窗口（3m/6m/1y/3y/5y/10y）** 全量回测比较的分析系统。

覆盖 **5039 只基金**、**~800 万行日频净值数据**，结果通过 Streamlit Web 应用交互展示。

## 功能

- **全市场策略排名** — 每只基金各窗口下的最优策略及完整回测指标
- **7 种定投策略对比** — 年化收益、最大回撤、夏普比率、胜率等
- **多时间窗口** — 3m/6m/1y/3y/5y/10y，侧边栏一键切换
- **单只基金深度分析** — 策略收益曲线对比、vs 一次性投入
- **基金类型分类分析** — 按类型统计最优策略分布、平均绩效
- **策略参数调优** — 网格搜索最佳参数组合
- **数据自动更新** — 从天天基金 API 拉取最新净值
- **宏观分析（@analyst）** — 结合产业政策、货币政策、地缘政治等 7 大维度综合分析

## 定投策略

| 策略 | 说明 |
|------|------|
| 定期定额(月) | 每月固定金额投资，基准策略 |
| 定期定额(周) | 每周固定金额（月投金额 1/4） |
| 均线偏离法 | NAV 低于均线多投，高于均线少投，偏离越大调整幅度越大 |
| 回撤加仓法 | 从近期高点回撤超过阈值时加倍投入 |
| 止盈策略 | 累计收益达目标后全部赎回，重新开始定投 |
| MA 停投法 | NAV 高于均线一定比例时暂停当月投资 |
| 价值平均法 | 每月使持仓总市值增加固定金额，低位多买、高位少买/卖出 |

## 数据流

```
天天基金 API
     │
     ▼
┌─ downloader.py ─────────────────────┐
│  筛选: 成立>1年, 规模>2亿, 目标类型  │
│  股票型/混合型/指数型/QDII          │
└──────────┬──────────────────────────┘
           │ 5039 只基金
           ▼
┌─ NAV 数据 (~800 万行) ──────────────┐
│  data/funding.db (nav 表)           │
│  data/nav/*.csv (备份)              │
└──────────┬──────────────────────────┘
           │
           ▼
┌─ strategies.py 回测引擎 ────────────┐
│  run_all_strategies_multi_window()  │
│  4 窗口 × 7 策略 × 5039 基金       │
│  ThreadPoolExecutor(30) 并行       │
└──────────┬──────────────────────────┘
           │
           ▼
┌─ DB (ranking + strategy_detail) ───┐
│  每基金每窗口: 最佳策略排名         │
│  每基金每窗口×策略: 完整回测指标    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─ Streamlit Web (app.py) ───────────┐
│  全市场概况 │ 基金分析 │ 参数调优   │
│  分类分析                           │
└─────────────────────────────────────┘
```

## 环境配置

### 前置要求

- Python 3.11
- Miniconda / Anaconda

### 安装

```powershell
conda create -n funding python=3.11 -y
conda activate funding
pip install -r requirements.txt
```

### 数据准备

系统自带预计算数据（SQLite 数据库）。如需更新净值：

```powershell
python src/downloader.py
```

然后重新运行全量回测：

```powershell
python src/analysis.py
```

> 全量回测约 1.5-2 小时（ThreadPoolExecutor 30 并发）。

## 运行

### Web 界面

```powershell
streamlit run src/app.py --server.port 8501
```

打开 `http://localhost:8501`，4 个功能页面：

| 页面 | 功能 |
|------|------|
| 全市场概况 | 策略分布饼图、风险-收益散点图、类型对比、排名表 |
| 基金分析 | 搜索基金，7 策略对比 + 累计收益曲线 vs 一次性投入 |
| 参数调优 | 选择策略，滑块调参，实时回测 |
| 分类分析 | 类型×策略交叉表、平均绩效、跑赢比例、相关性 |

### CLI 工具

```powershell
# 单只基金深度分析
python src/fund_report.py <基金代码>
python src/fund_report.py <基金代码> --buy-fee 0.0015 --sell-fee 0.005

# 基金类型分类分析（可指定窗口）
python src/analysis_categories.py      # 默认 3y
python src/analysis_categories.py 10y

# 策略参数网格调优
python src/param_tune.py

# 查看数据库
python -c "import sys; sys.path.insert(0,'src'); from db import get_conn; import pandas as pd; print(pd.read_sql('SELECT code,window,best_strategy FROM ranking LIMIT 10', get_conn()))"

# 宏观分析计划生成
python -c "import sys; sys.path.insert(0,'src'); from macro import get_macro_plan; p=get_macro_plan('004320'); print(p['dimensions'], p['search_queries'])"
```

## 项目结构

```
funding project/
├── src/
│   ├── strategies.py           # 回测引擎 + 7 种定投策略
│   ├── analysis.py             # 全市场多窗口回测主程序
│   ├── analysis_categories.py  # 基金类型分类统计
│   ├── analysis_compare_windows.py  # 窗口间策略一致性分析
│   ├── fund_report.py          # 单只基金 CLI 报告
│   ├── viz.py                  # matplotlib 可视化
│   ├── param_tune.py           # 参数网格搜索调优
│   ├── downloader.py           # 天天基金 API 数据下载
│   ├── db.py                   # SQLite 数据库访问层
│   ├── macro.py                # 宏观分析辅助（7 维度映射）
│   └── app.py                  # Streamlit Web 应用
├── data/
│   ├── funding.db              # SQLite 数据库（含全部回测结果）
│   ├── fund_list_filtered.csv  # 筛选后的基金列表
│   ├── nav/                    # 净值 CSV 备份
│   ├── charts/                 # 可视化图表
│   └── param_tune/             # 参数调优结果
├── .opencode/
│   └── agent/
│       └── analyst.md          # analyst agent 说明（未启用，见 opencode.json）
├── .streamlit/config.toml      # Streamlit 配置
├── opencode.json               # opencode 配置（analyst agent 定义）
├── AGENTS.md                   # 开发约定（AI 辅助用）
└── README.md
```

## 关键发现（2023-2026 回测期）

- **价值平均法**在约 90% 的基金上综合得分最高，是整体最优策略
- 指数型基金最优策略分布最分散 — 均线偏离法、MA 停投法各有 7-9% 的基金最佳
- QDII 基金受海外市场特性影响，定投收益普遍低于一次性投入
- 申购 0.15% + 赎回 0.5% 的费用对年化收益影响约 0.5 个百分点
- **窗口间策略一致性**: 3m↔6m 65.8%, 3y↔5y 89.6%, 3m↔10y 仅 17.8%
- **3m 窗口**周定投占 62%；**6m+**价值平均法占 71%→95%
- **1y 窗口**是均线偏离法和 MA 停投法的 activation 分界点

## 技术栈

| 组件 | 技术 |
|------|------|
| 数据源 | 天天基金（东方财富）API — `efinance` |
| 数据处理 | pandas 3.0+, numpy |
| 数据库 | SQLite（`data/funding.db`） |
| 并行计算 | `ThreadPoolExecutor(max_workers=30)` |
| 可视化 | matplotlib |
| Web 界面 | Streamlit |
| 进度显示 | tqdm |
