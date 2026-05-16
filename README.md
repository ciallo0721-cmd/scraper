# 新番数据库 📺

每月自动爬取当季新番信息，通过 GitHub Pages 提供 JSON 数据查询。

## 在线访问

| 地址 | 内容 |
|------|------|
| `https://ciallo0721-cmd.github.io/scraper/` | 可视化新番列表 |
| `https://ciallo0721-cmd.github.io/scraper/data.json` | 最新季度 JSON 数据 |
| `https://ciallo0721-cmd.github.io/scraper/history/YYYY-MM.json` | 历史月份归档 |

## JSON 格式

```json
{
  "generated_at": "2026-01-31",
  "season": "2026年1月 冬番",
  "total": 48,
  "anime": [
    {
      "name": "名称（日文）",
      "name_en": "English Title",
      "date": "2026年1月 冬番",
      "start_date": "2026-01-05",
      "tag": "Action、Fantasy、School",
      "character": "キャラA、キャラB",
      "author": "制作公司",
      "episodes": 12,
      "status": "RELEASING",
      "score": 82
    }
  ]
}
```

## 自动化说明

- **触发时间**：每月 28-31 日 UTC 16:00（北京时间 00:00）
- **判断逻辑**：Python 脚本检测是否为当月最后一天，否则退出
- **手动触发**：在 Actions → Monthly Anime Scraper → Run workflow，可指定月份

## 配置 GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：

| 变量名 | 内容 |
|--------|------|
| `SMTP_USER` | 发件人 QQ 邮箱，如 `3627742771@qq.com` |
| `SMTP_PASS` | QQ 邮箱授权码（不是登录密码，在邮箱设置→账户→开启 SMTP 获取） |
| `TO_EMAIL`  | 收件人邮箱（可与发件人相同） |

## 启用 GitHub Pages

1. 仓库 Settings → Pages
2. Source 选 **Deploy from a branch**
3. Branch 选 `main`，目录选 `/docs`
4. 保存后等待 1-2 分钟即可访问

## 本地测试

```bash
pip install -r requirements.txt

# 强制爬取 2026 年 1 月数据
FORCE_MONTH=1 FORCE_YEAR=2026 python scraper.py

# 发送测试邮件
SMTP_USER=xxx@qq.com SMTP_PASS=授权码 TO_EMAIL=xxx@qq.com python send_email.py
```

## 数据来源

[AniList GraphQL API](https://anilist.gitbook.io/anilist-apiv2-docs/) — 免费公开，无需认证
