# Anime Scraper

每月末自动从 [AniList GraphQL API](https://anilist.gitbook.io/anilist-apiv2-docs/) 抓取当季新番，发布到 GitHub Pages 并发送邮件月报。

## Live

| URL | Description |
|-----|-------------|
| `/` | Visual anime list |
| `/data.json` | Latest season JSON |
| `/history/YYYY-MM.json` | Archived months |

## JSON Format

```json
{
  "generated_at": "2026-01-31",
  "month": "2026-01",
  "season": "2026年1月 冬番",
  "season_en": "WINTER 2026",
  "total": 48,
  "warnings": [],
  "anime": [
    {
      "name": "葬送のフリーレン",
      "name_en": "Frieren: Beyond Journey's End",
      "date": "2026年1月 冬番",
      "start_date": "2026-01-05",
      "tag": "Adventure、Drama、Fantasy",
      "character": "フリーレン、ヒンメル",
      "author": "MADHOUSE",
      "episodes": 28,
      "status": "RELEASING",
      "score": 82
    }
  ]
}
```

### 顶层字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `generated_at` | string | 脚本运行日期（ISO 8601） | `"2026-01-31"` |
| `month` | string | 归档键，对应 `history/<month>.json` | `"2026-01"` |
| `season` | string | 中文展示用季度标签 | `"2026年1月 冬番"` |
| `season_en` | string | AniList 季度枚举 + 年份 | `"WINTER 2026"` |
| `total` | number | 收录作品总数 | `48` |
| `warnings` | array | 本次抓取的告警列表，正常为空 | `[]` |
| `anime` | array | 作品列表，按人气降序 | — |

### `anime[]` 单项字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `name` | string | 显示名，日文原名优先 | `"葬送のフリーレン"` |
| `name_en` | string | 英文名，缺失时回落到 romaji | `"Frieren: Beyond Journey's End"` |
| `date` | string | 所属季度标签，同顶层 `season` | `"2026年1月 冬番"` |
| `start_date` | string | 首播日期，未知部分用 `?` 占位 | `"2026-01-05"` |
| `tag` | string | 官方 genres 优先 + 高分社区标签 | `"Adventure、Drama、Fantasy"` |
| `character` | string | 按 ROLE 排序的前 6 位角色 | `"フリーレン、ヒンメル"` |
| `author` | string | 主制作公司，多个用顿号连接 | `"MADHOUSE"` |
| `episodes` | number \| null | 集数，未公布为 `null` | `28` |
| `status` | string | 播出状态枚举 | `"RELEASING"` |
| `score` | number \| null | AniList 平均分（0-100） | `82` |

`status` 取值：`NOT_YET_RELEASED` / `RELEASING` / `FINISHED` / `CANCELLED` / `HIATUS`。

## Run Locally

```bash
pip install -r requirements.txt
python scraper.py
```

非月末运行时会自动跳过。调试时可用环境变量强制：

| 变量 | 作用 |
|------|------|
| `FORCE_RUN=1` | 忽略月末检查 |
| `FORCE_MONTH=7` | 指定月份；未给 `FORCE_YEAR` 时按「离今天最近的同名月份」推断年份 |
| `FORCE_YEAR=2026` | 指定年份 |

产物：`docs/data.json`、`docs/history/YYYY-MM.json`、`summary.txt`。

发送邮件（可选，需先配置下方 SMTP 变量）：

```bash
python send_email.py
```

## Configuration

GitHub Secrets：

| Name | Description |
|------|-------------|
| `SMTP_USER` | 发件人 QQ 邮箱 |
| `SMTP_PASS` | QQ 邮箱授权码（非登录密码） |
| `TO_EMAIL` | 收件人邮箱 |
| `SITE_URL` | 可选，邮件里数据直链的前缀，默认 GitHub Pages 地址 |

Pages 需从 `main` / `docs` 启用。

## Behavior Notes

- 分页按 `hasNextPage` 动态推进，最多 20 页兜底；翻页间隔 2 秒规避 AniList 速率限制
- 网络抖动 / 429 / 5xx 自动指数退避重试 3 次，耗尽后记录告警而非直接崩溃
- 写入前做字段自检，校验不通过则**不落盘**，避免用空数据覆盖站点
- 查询固定 `isAdult: false`，输出端再做一次成人内容二次过滤
- 邮件发送失败不会阻塞数据推送：工作流用 `always()` 保证数据落地，同时把运行标记为失败提醒

## Data Source

[AniList GraphQL API](https://anilist.gitbook.io/anilist-apiv2-docs/) — Free, no auth required.
