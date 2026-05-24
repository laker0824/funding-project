# TODO.md — 基金定投策略回测系统改进清单

> 最后更新: 2026-05-24
> 优先级: 🔴 Critical > 🟠 Major > 🟡 Minor > 💡 Suggestion

---

## 🔴 Critical（5 项）

### 1. 分红处理 — acc_nav 未用于回测

**问题**: `nav` 表同时存了 `nav`（单位净值）和 `acc_nav`（累计净值），但回测引擎只用 `nav`。基金分红除权日 `nav` 下跌但 `acc_nav` 不变，系统会误判为亏损。

**影响**: 分红型基金的回测收益被系统性低估。

**方案**: 回测计算收益率时改用 `acc_nav` 或分红调整后的净值。

**估算**: 16-24h

---

### 2. 无基准对比

**问题**: 没有沪深300/中证500/中证1000 等指数数据，无法计算超额收益、Beta、Alpha、信息比。

**影响**: 无法判断基金是"真的优秀"还是"β 驱动的虚假繁荣"。

**方案**: `src/downloader.py` 新增指数下载 → DB 新增 `index_nav` 表 → `calc_metrics` 新增 beta/alpha → app 图表叠加基准线。

**估算**: 16-24h

---

### 3. 无基金搜索/筛选

**问题**: app 基金分析页只有 top50 下拉框 + 手动输入基金代码，5039 只基金几乎不可查找。

**方案**: 搜索框支持代码/名称模糊匹配 + 筛选器（类型/规模/年限）。

**估算**: 8-16h

---

### 4. 无自定义策略 UI

**问题**: 只能在代码层面新增策略，用户无法在 app 中组合参数生成新策略。

**方案**: app 新增"策略构建器"页面，可视化组合定投频率+金额调整规则+止盈止损条件。

**估算**: 24-40h

---

### 5. 核心函数零测试

**问题**: `run_all_strategies()` 和 `run_all_strategies_multi_window()` 没有单元测试。

**方案**: mock `load_nav` 返回固定净值数据，测试各窗口长度和策略返回格式。

**估算**: 8h

---

## 🟠 Major（13 项）

### 6. DB 函数静默吞异常

**文件**: `src/db.py` — 12 处 `except Exception: pass`

**方案**: 改为 `logger.exception()` 或至少 `print` 到 stderr。

**估算**: 4h

### 7. 回测重复执行

- `viz.py:plot_strategy_curves` 对同一组策略跑了 3 遍（21 次回测）
- `app.py` 先 `run_all_strategies` 又在 Plotly 图里逐策略 `run_backtest`

**方案**: 缓存 `result_df` 结果，子图共享。

**估算**: 2h

### 8. `load_nav` 重复调用

**问题**: app 基金分析页连续调了 3 次 `load_nav`。

**方案**: 用 `@st.cache_data` 或显式传参复用。

**估算**: 1h

### 9. 无组合分析

**问题**: 只能看单只基金，无法构建多基金组合。

**方案**: 新增组合构建页面，支持多基金加权组合 + Markowitz 优化。

**估算**: 16-24h

### 10. 无基金横向对比

**方案**: 支持选 2-3 只基金并排比较收益曲线和指标。

**估算**: 8-16h

### 11. 无数据导出

**方案**: 每个 `st.dataframe` 后加 `st.download_button`（CSV/Excel）。

**估算**: 4-8h

### 12. 无高级风控指标

**缺少**: VaR/CVaR/Beta/Alpha/Sortino/信息比。

**方案**: 追加到 `calc_metrics` 并在 app 展示。

**估算**: 4-8h

### 13. 无市场状态识别

**方案**: 基于 200 日均线和波动率聚类识别牛/熊/震荡市，给出策略建议。

**估算**: 8-16h

### 14. 无交易明细展开表

**方案**: 加 `st.expander` 展示 `result_df` 中 `amount > 0` 的行。

**估算**: 2-4h

### 15. 无收藏/关注

**方案**: 用 `st.experimental_user` 或本地 JSON 存储用户收藏。

**估算**: 8-12h

### 16. 8 个模块零测试覆盖

| 模块 | 函数数 | 估算 |
|------|--------|------|
| `app.py` | 6 | 16h |
| `viz.py` | 9 | 12h |
| `fund_report.py` | 7 | 8h |
| `analysis.py` | 3 | 8h |
| `analysis_categories.py` | 8 | 8h |
| `analysis_compare_windows.py` | 5 | 4h |
| `param_tune.py` | 5 | 8h |
| `downloader.py` | 7 | 12h |

**方案**: 按文件分组逐步覆盖，优先测试 `app.py` 和 `viz.py`。

**估算**: 40-80h

### 17. Top-50 基金限制

**文件**: `app.py:244` — `.head(50)`

**方案**: 改为可搜索下拉框。

**估算**: 2h

---

## 🟡 Minor（6 项）

### 18. 重复魔法数字

`BASE_AMOUNT=1000` 在 `strategies.py` / `app.py` / `viz.py` / `fund_report.py` / `param_tune.py` 重复定义。

**方案**: 统一到常量模块。

**估算**: 1h

### 19. 未使用的 import（6 处）

- `strategies.py`: `from datetime import datetime`
- `app.py`: `from io import BytesIO`
- `app.py`: `_CN_SATURATED`（定义未使用）
- `analysis.py`: `from datetime import datetime, timedelta`
- `analysis_categories.py`: `import numpy as np`
- `param_tune.py`: `from concurrent.futures import as_completed`

**估算**: 1h

### 20. `efinance` 在 requirements 但从未 import

**估算**: 0.5h（删除或补 import）

### 21. `fig_to_png` 死代码（`app.py:118-122`）

**估算**: 0.5h

### 22. 缺失基金类型

债券型/商品型（非QDII）未覆盖。

**估算**: 1h（配置改动）

### 23. 硬编码策略名（`analysis_compare_windows.py:12-13`）

**方案**: 从 DB 读取而非硬编码。

**估算**: 0.5h

---

## 💡 Suggestion（2 项）

### 24. 暗色模式

Streamlit 原生支持，加一个 toggle 即可。

**估算**: 2h

### 25. AI/ML 策略建议

集成 LLM，根据基金特征推荐最优策略。

**估算**: 40-80h

---

## 建议执行路线

```
Q1（数据正确性）
  - 🔴 分红处理（acc_nav）
  - 🔴 基准指数（CSI300）
  - 🟠 DB 异常处理

Q2（可用性提升）
  - 🔴 基金搜索/筛选
  - 🟠 数据导出
  - 🟠 交易明细展开
  - 🟠 性能优化（缓存回测结果）
  - 🟡 清理重复常量和死代码

Q3（功能扩展）
  - 🟠 高级风控指标
  - 🟠 市场状态识别
  - 🟠 基金横向对比
  - 🟠 收藏/关注

Q4（高级特性）
  - 🔴 自定义策略
  - 🟠 组合分析
  - 💡 AI/ML 策略建议
```
