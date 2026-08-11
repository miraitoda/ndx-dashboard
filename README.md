# 纳指100 每日收盘 Dashboard

每天自动抓取纳斯达克100指数成分股数据，生成一个自包含的 HTML 页面，部署到 GitHub Pages。

## 在线预览

部署后访问: `https://你的用户名.github.io/ndx-dashboard/`

## 项目结构

```
ndx-dashboard/
├── .github/workflows/update.yml   # 定时自动更新
├── ndx_components.py              # 100只成分股列表 + 行业分类 + 权重
├── fetch_data.py                  # 数据抓取 + HTML 生成
├── requirements.txt               # Python 依赖
└── docs/                          # GitHub Pages 部署目录
    └── index.html                 # 生成的最终页面
```

## 快速开始

### 1. 创建 GitHub 仓库

- 新建一个公开仓库，命名为 `ndx-dashboard`
- 把本项目的所有文件上传到这个仓库

### 2. 开启 GitHub Pages

- 进入仓库 Settings -> Pages
- Source 选择 "Deploy from a branch"
- Branch 选择 `gh-pages`，文件夹选 `/ (root)`
- 保存

### 3. 手动运行一次

- 进入仓库 Actions 标签页
- 找到 "Update NDX Dashboard" 工作流
- 点击 "Run workflow" 手动触发一次
- 等待约 2-3 分钟，页面就会生成

### 4. 自动更新

- 工作流已配置每天北京时间 **09:00** 自动运行
- 美股夏令时收盘是北京时间凌晨 4:00，9点数据最稳定
- 如需调整时间，修改 `.github/workflows/update.yml` 中的 cron 表达式

### 5. 本地测试

```bash
pip install -r requirements.txt
python fetch_data.py
# 打开 docs/index.html 查看效果
```

## 数据来源

- **个股数据**: Yahoo Finance (via yfinance)
- **指数历史**: Yahoo Finance (^NDX)
- **成分股权重**: 基于 QQQ/NDX 市值权重硬编码，每季度需手动更新 `ndx_components.py`

## 页面包含的图表

| 图表 | 说明 |
|------|------|
| 个股权重饼图 | Top 15 + 其他，红涨绿跌，面积=权重 |
| 行业权重饼图 | 9大行业，红涨绿跌，面积=权重 |
| 涨跌分布柱图 | 100只股票按涨跌幅区间分布 |
| 行业表现柱图 | 各行业加权平均涨跌幅对比 |
| 30日走势线图 | 纳指100近30日收盘价连线 |
| 成分股涨跌网格 | 100只股票一览，悬停看详情 |

## 注意事项

1. **成分股调仓**: 纳指100每季度调仓，需手动更新 `ndx_components.py` 中的股票列表
2. **权重更新**: 权重会随市值变化，建议每季度同步一次
3. **数据缺失**: yfinance 偶尔会有个别股票数据缺失，页面会显示 "部分缺失" 状态
4. **免费额度**: yfinance 完全免费，但请合理控制请求频率

## 自定义

- 修改 `fetch_data.py` 中的 `max_batch` 可以调整每次请求的股票数量
- 修改 `ndx_components.py` 可以增删股票或调整行业分类
- HTML 样式全部内联，直接修改 `fetch_data.py` 中的模板即可

## License

MIT
