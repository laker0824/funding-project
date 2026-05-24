# 基金定投策略回测分析系统

基于中国市场公募基金历史净值数据，对7种定投策略进行全量回测比较的分析系统。

## 项目结构

```
funding project/
├── src/
│   ├── strategies.py           # 回测引擎 + 7种定投策略
│   ├── analysis.py             # 全市场回测主程序
│   ├── analysis_categories.py  # 基金分类统计分析
│   ├── fund_report.py          # 单只基金深度分析 (CLI)
│   ├── viz.py                  # 可视化模块 (matplotlib)
│   ├── param_tune.py           # 策略参数网格搜索调优
│   ├── downloader.py           # 数据下载 (基金列表+净值)
│   └── app.py                  # Streamlit Web 应用
├── data/
│   ├── dca_ranking.csv         # 993只基金排名结果
│   ├── dca_strategy_detail.csv # 6951条策略明细
│   ├── fund_list_filtered.csv  # 筛选后的基金列表
│   ├── nav/                    # 基金净值文件 (CSV)
│   ├── charts/                 # 可视化图表 (PNG)
│   └── param_tune/             # 参数调优结果 (CSV)
├── .streamlit/config.toml      # Streamlit 配置
├── requirements.txt
├── AGENTS.md
└── README.md
```

## 环境配置

```powershell
# 创建 conda 环境
conda create -n funding python=3.11 -y
conda activate funding

# 安装依赖
pip install -r requirements.txt
streamlit run src/app.py  # Web 界面
```

## 定投策略

| 策略 | 说明 |
|------|------|
| 定期定额(月) | 每月固定金额，基准策略 |
| 定期定额(周) | 每周固定金额（月投的1/4） |
| 均线偏离法 | NAV低于均线多投，高于少投 |
| 回撤加仓法 | 从高点回撤超阈值时加码 |
| 止盈策略 | 达目标收益赎回，重新开始 |
| MA停投法 | NAV高于均线一定比例时停投 |
| 价值平均法 | 每月使总市值增加固定金额 |

## 使用方式

### CLI 模式

```powershell
# 全市场回测 (已运行过，可直接查看结果)
python src/analysis.py

# 分类统计分析
python src/analysis_categories.py

# 单只基金深度分析
python src/fund_report.py 960033
python src/fund_report.py 960033 --buy-fee 0.0015 --sell-fee 0.005

# 参数调优
python src/param_tune.py
```

### Web 模式

```powershell
" " | python -m streamlit run src/app.py --server.port 8501
```

打开 `http://localhost:8501`，4个功能页面：
1. **全市场概况** — 策略分布、类型对比、散点图、排名表
2. **基金分析** — 搜索基金，7策略对比 + 累计收益曲线
3. **参数调优** — 选策略，滑条调参，实时回测
4. **分类分析** — 交叉表、平均绩效、跑赢比例、相关性

### 数据更新

```powershell
python src/downloader.py
```

## 关键发现 (2023-2026回测期)

- **价值平均法**在89.8%的基金上综合得分最高
- 指数型基金策略分布最分散（均线偏离法 9%，MA停投法 7%）
- QDII基金定投收益普遍低于一次性投入
- 申购0.15%+赎回0.5%的费用对年化收益影响约0.5%

## 依赖

- efinance — 东方财富基金数据接口
- pandas, numpy — 数据处理
- matplotlib — 图表
- streamlit — Web 界面
- tqdm — 进度条
