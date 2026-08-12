# 纳指100 每日收盘 Dashboard

> 基于 Yahoo Finance 数据，每日自动更新的纳斯达克100指数可视化仪表盘。

🔗 **在线访问**: [https://miraitoda.github.io/ndx-dashboard/](https://miraitoda.github.io/ndx-dashboard/)

---

## 功能特性

### 核心数据
- **实时行情**：纳指100收盘点位、涨跌幅、涨跌家数统计
- **个股权重饼图**：Top 15 + 其他，面积=权重，颜色=涨跌
- **行业权重饼图**：各行业权重分布，颜色=涨跌
- **涨跌分布柱图**：100只成分股按涨跌幅区间分布
- **行业表现柱图**：各行业按权重加权平均涨跌幅，零轴居中发散条形图
- **30日走势线图**：近30个交易日收盘价连线
- **成分股涨跌网格**：100只个股一览，绿涨红跌

### AI 行情总结
每日自动生成专业行情点评，基于真实数据（涨跌家数、领涨领跌行业、龙头个股），零成本无需 API Key。

### 历史回溯
- 支持前后日导航（← 前一日 / 后一日 →）
- 滚动保留最近 **5 个交易日**快照
- 非交易日自动跳过，不淘汰历史数据
- 每个历史页面独立配色（绿涨红跌跟随当日行情）

### 交互体验
- **深色/日间双主题**：自动跟随系统 + 手动切换
- **实时市场状态**：根据客户端时间自动判断"开盘中"/"已收盘"
- **刷新按钮**：一键刷新页面
- **Tooltip 悬停提示**：个股/行业/走势详细数据

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 数据抓取 | Python + yfinance (Yahoo Finance) |
| 自动化 | GitHub Actions (UTC 22:00 = 北京时间 06:00) |
| 前端 | 纯 HTML + CSS + SVG（无框架依赖） |
| 部署 | GitHub Pages |

---

## 数据更新机制

```
GitHub Actions (每天北京时间 06:00)
    ↓
GitHub 服务器抓取 Yahoo Finance 数据
    ↓
generate_summary() 生成本地 AI 行情总结
    ↓
生成 index.html（最新）
生成 history/YYYY-MM-DD.html（快照）
    ↓
滚动保留 5 个交易日 → 删除过期快照
    ↓
GitHub Pages 自动部署
```

> 用户在中国大陆无法直接访问 Yahoo Finance，依靠 GitHub 服务器在国外完成数据抓取。

---

## 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/miraitoda/ndx-dashboard.git
cd ndx-dashboard

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行数据抓取
python fetch_data.py

# 4. 本地预览
cd docs && python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

---

## 文件结构

### 仓库源码（main 分支）
```
.
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Actions 定时任务
├── fetch_data.py               # 数据抓取 + HTML 生成脚本
├── ndx_components.py           # 纳指100成分股列表
└── requirements.txt            # Python 依赖
```

### 生成文件（本地运行后 / gh-pages 分支）
```
docs/                           # GitHub Pages 发布目录
├── index.html                  # 最新数据页面
└── history/                    # 历史快照（最多保留5个交易日）
    ├── 2026-08-12.html
    ├── 2026-08-12.json
    └── ...
```

> `docs/` 由 GitHub Actions 运行时自动生成并部署到 **gh-pages 分支**，main 分支不包含此目录。

---

## 配色规则

| 颜色 | 含义 |
|---|---|
| 🟢 绿色 `#089981` | 上涨/正值 |
| 🔴 红色 `#f23645` | 下跌/负值 |
| 全局光晕 | 根据当日纳指涨跌动态变色 |

---

## 注意事项

1. **数据延迟**：Yahoo Finance 数据可能有 15-30 分钟延迟，仅供参考
2. **非交易日**：周末/节假日 Action 仍会触发，但数据不足 80 只成分股时不生成新快照
3. **成分股调整**：纳指100成分股每季度调整，需同步更新 `ndx_components.py`
4. **投资建议**：本页面仅供数据可视化参考，不构成任何投资建议

---

## License

MIT
