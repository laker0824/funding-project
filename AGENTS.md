# AGENTS.md — 项目约定

## 环境

- Python 3.11 conda 环境，名称 `funding`
- 使用 `"D:\minicoda3\envs\funding\python.exe"` 直接运行（`conda run` 有 GBK 编码问题）
- Streamlit 使用 `Start-Process -NoNewWindow -FilePath "D:\minicoda3\envs\funding\python.exe" -ArgumentList "-m","streamlit","run","src/app.py","--server.port","8501" -WorkingDirectory "D:\Project\funding project"` 启动

## 项目规范

### 编码风格
- 无注释代码（除非必要）
- 中文变量名/注释用中文，代码逻辑用英文
- pandas 3.0+，注意 Copy-on-Write 行为，使用 `.loc` 而非链式赋值

### 文件结构
- `src/` — 所有源代码
- `data/` — 数据文件、图表、调优结果、SQLite 数据库
- `.streamlit/config.toml` — Streamlit 配置（已禁用用量统计）
- `opencode.json` — opencode 配置，含 inline analyst agent 定义
- `.opencode/agent/analyst.md` — analyst agent 参考文档（未启用）

### 宏观分析 (`src/macro.py`)
- 7 大维度: 产业政策/货币政策/地缘政治/A股市场环境/行业监管/汇率与资本/全球产业链
- 16 条基金类型→维度映射规则
- `get_macro_plan(code)` → 返回维度列表 + 搜索查询
- `build_queries()` — 自动推测产业关键词，生成搜索查询
- 仅供 `@analyst` agent 调用，不在 Streamlit 中使用

### 数据库 (`src/db.py`)
- SQLite 数据库，路径 `data/funding.db`
- 4 张表：
  - `funds` — 基金基本信息（5039 只）
  - `nav` — 日频净值数据（~800 万行），PK `(code, date)`
  - `ranking` — 每只基金每个窗口的最佳策略排名，PK `(code, window)`
  - `strategy_detail` — 每只基金每个窗口 × 7 策略的完整回测明细，PK `(code, strategy, window)`
- 所有 `save_*` 函数使用 `to_sql(if_exists="replace")`，覆盖写入
- `load_nav(code)` 读 DB 查询，若为空则回退读 CSV 文件
- `save_nav_batch(rows)` 使用 `INSERT OR REPLACE` 批量写入

### 策略函数 (`src/strategies.py`)
- 回测入口: `run_all_strategies(code, start_date=None, end_date=None, years=None, buy_fee_rate=0.0, sell_fee_rate=0.0, min_period=200)`
- 多窗口入口: `run_all_strategies_multi_window(code, windows=(0.25, 0.5, 1, 3, 5, 10), buy_fee_rate=0.0, sell_fee_rate=0.0)`
  - 每个窗口的 `min_rows = max(50, round(years * 200))`（3m=50, 6m=100, 1y=200, 3y=600, 5y=1000, 10y=2000）
- 通用引擎: `run_backtest(nav_df, schedule, get_amount_fn, strategy_name, buy_fee_rate, sell_fee_rate)`
- 新增策略需在 `strategies.py` 添加策略工厂函数，并在 `run_all_strategies` 中注册

### 可视化
- `viz.py` 函数均 `return fig`，供 Streamlit 直接使用
- 图表保存至 `data/charts/`
- 字体自动检测 Windows 中文（微软雅黑>黑体>等线>Noto Sans SC）

### Streamlit 应用 (`src/app.py`)
- 4 个页面通过 `selectbox` 切换
- 侧边栏有**时间窗口选择器**（3m/6m/1y/3y/5y/10y），所有页面跟随切换
- `load_rank(window)` / `load_detail(window)` 使用 `@st.cache_data` 缓存
- 参数调优页通过 `STRATEGIC_CONFIG` 字典配置策略参数网格

### 回测性能
- `ThreadPoolExecutor(max_workers=min(len(codes), os.cpu_count()*4))` — 顶层并行
- `run_all_strategies_multi_window` 内部窗口级并行: `ThreadPoolExecutor(max_workers=min(len(windows), 6))`
- `run_all_strategies` 支持 `nav_df` 参数传入，避免窗口间重复加载净值
- `ProcessPoolExecutor` 在 Windows 上会死锁（`spawn` 模式 + SQLite 竞争）

### 数据下载 (`src/downloader.py`)
- 基金成立筛选条件: `成立>1年`（之前为 3 年）
- 规模筛选: `>2亿`
- 目标类型见 `TARGET_TYPES`（股票型、混合型、指数型、QDII 等）
- 净值下载并行写 DB + CSV

## 常用命令

```powershell
# 运行 Web 应用（直接打开后在浏览器访问 http://localhost:8501）
Start-Process -NoNewWindow -FilePath "D:\minicoda3\envs\funding\python.exe" -ArgumentList "-m","streamlit","run","src/app.py","--server.port","8501" -WorkingDirectory "D:\Project\funding project"

# 单只基金分析
"D:\minicoda3\envs\funding\python.exe" src/fund_report.py 基金代码

# 参数调优
"D:\minicoda3\envs\funding\python.exe" src/param_tune.py

# 分类分析（可指定窗口，默认 3y）
"D:\minicoda3\envs\funding\python.exe" src/analysis_categories.py 10y

# 全量回测（多窗口 3m/6m/1y/3y/5y/10y，约 1.5-2h）
"D:\minicoda3\envs\funding\python.exe" src/analysis.py

# 数据下载 & 筛选
"D:\minicoda3\envs\funding\python.exe" src/downloader.py

# CSV → SQLite 迁移
"D:\minicoda3\envs\funding\python.exe" src/migrate_to_db.py

# 查看数据库
"D:\minicoda3\envs\funding\python.exe" -c "import sys; sys.path.insert(0,'src'); from db import get_conn; import pandas as pd; c=get_conn(); print(pd.read_sql('SELECT * FROM ranking LIMIT 5', c)); c.close()"
```
