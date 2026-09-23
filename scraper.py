"""
scraper.py
每月末自动从 AniList GraphQL API 爬取当季新番信息
输出到 docs/data.json 和 docs/history/YYYY-MM.json
"""

from __future__ import annotations

import calendar
import datetime
import json
import os
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ANILIST_URL = "https://graphql.anilist.co"

# ── 抓取参数 ──────────────────────────────────────────────────────────────
PER_PAGE = 50            # 每页条数（AniList 上限 50）
MAX_PAGES = 20           # 分页安全阀：hasNextPage 异常时兜底，防止死循环
PAGE_DELAY = 2.0         # 翻页之间的礼貌延迟（秒），规避 AniList 速率限制
REQUEST_TIMEOUT = 20     # 单次请求超时（秒）
RETRY_TOTAL = 3          # 失败重试次数（指数退避）
MAX_CHARACTERS = 6       # 输出保留的角色数，需与 GraphQL 里的 perPage 一致

# ── 标签策略 ──────────────────────────────────────────────────────────────
TAG_MIN_RANK = 60        # 额外标签的最低社区认可度
MAX_EXTRA_TAGS = 5       # 除 genres 外最多补充几个标签
MAX_TAGS = 8             # 标签字段总上限（genres 优先，稳定性更好）

SEASON_CN = {
    "WINTER": "冬番",
    "SPRING": "春番",
    "SUMMER": "暑番",
    "FALL":   "秋番",
}

GRAPHQL_QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage currentPage }
    media(
      season: $season
      seasonYear: $year
      type: ANIME
      sort: POPULARITY_DESC
      isAdult: false
    ) {
      title { romaji native english }
      season
      seasonYear
      genres
      tags { name rank isMediaSpoiler }
      characters(sort: ROLE, perPage: 6) {
        nodes { name { full native } }
      }
      studios(isMain: true) {
        nodes { name }
      }
      startDate { year month day }
      episodes
      status
      isAdult
      averageScore
      popularity
    }
  }
}
"""

# 本次运行收集到的告警，会写入 data.json 供前端 / 邮件展示
WARNINGS: list[str] = []


def warn(message: str) -> None:
    """记录一条告警。

    在 GitHub Actions 环境下额外输出 ::warning:: 注解，便于在工作流 UI 上高亮定位。
    注意：这里刻意不让流程失败，避免后续写入步骤被跳过导致数据丢失。
    """
    WARNINGS.append(message)
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "[WARN] "
    print(prefix + message, file=sys.stderr)


def build_session() -> requests.Session:
    """构造带指数退避重试的 Session。

    只对网络抖动和 429 / 5xx 做重试；其余 4xx 说明请求本身有问题，立即失败更利于排查。
    urllib3 2.x 默认不会重试 POST，这里显式放行。
    """
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def month_to_season(month: int) -> str:
    """把月份映射到 AniList 的季度枚举。"""
    if month in (1, 2, 3):
        return "WINTER"
    if month in (4, 5, 6):
        return "SPRING"
    if month in (7, 8, 9):
        return "SUMMER"
    return "FALL"


def season_label(season: str, year: int, month: int) -> str:
    """生成中文展示标签，如「2026年7月 暑番」。"""
    return f"{year}年{month}月 {SEASON_CN.get(season, season)}"


def fetch_season(season: str, year: int, session: requests.Session | None = None) -> list[dict]:
    """按 hasNextPage 动态分页拉取指定季度的动画列表。

    任何一页失败都会记录告警并返回已获取的部分数据（不抛异常，保证月报不会整体中断）。
    返回原始 media 字典列表。
    """
    session = session or build_session()
    results: list[dict] = []
    page = 1

    while page <= MAX_PAGES:
        try:
            resp = session.post(
                ANILIST_URL,
                json={
                    "query": GRAPHQL_QUERY,
                    "variables": {"season": season, "year": year, "page": page},
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500:
                warn(f"第 {page} 页请求被拒绝：HTTP {status}，可能是查询语句或参数有误")
            else:
                warn(f"第 {page} 页请求失败：HTTP {status}（重试 {RETRY_TOTAL} 次后仍失败）")
            break
        except requests.RequestException as exc:
            warn(f"第 {page} 页网络异常（重试 {RETRY_TOTAL} 次后仍失败）：{exc}")
            break

        try:
            page_data = resp.json()["data"]["Page"]
            media = page_data.get("media") or []
        except (ValueError, KeyError, TypeError) as exc:
            warn(f"第 {page} 页响应结构异常，已中止分页：{exc}")
            break

        results.extend(media)
        print(f"   第 {page} 页：{len(media)} 条（累计 {len(results)}）")

        if not (page_data.get("pageInfo") or {}).get("hasNextPage"):
            break

        page += 1
        time.sleep(PAGE_DELAY)
    else:
        warn(f"分页已达到上限 {MAX_PAGES} 页，后面的数据可能被截断")

    return results


def _parse_title(title: dict | None) -> tuple[str, str]:
    """解析标题，返回 (显示名, 英文名)；显示名优先日文原名。"""
    title = title or {}
    name = title.get("native") or title.get("romaji") or "未知"
    name_en = title.get("english") or title.get("romaji") or ""
    return name, name_en


def _parse_tags(media: dict) -> str:
    """拼装标签字符串。

    先按 community rank 降序排列再截断，避免原始返回顺序打乱时丢掉高分标签；
    genres 是 AniList 官方分类，比用户标签稳定，因此优先级更高。
    """
    genres = [g for g in (media.get("genres") or []) if g]
    ranked = sorted(
        (t for t in (media.get("tags") or []) if not t.get("isMediaSpoiler", False)),
        key=lambda t: t.get("rank") or 0,
        reverse=True,
    )
    extra_tags = [
        t["name"] for t in ranked
        if (t.get("rank") or 0) >= TAG_MIN_RANK and t.get("name")
    ][:MAX_EXTRA_TAGS]
    return "、".join((genres + extra_tags)[:MAX_TAGS]) or "未分类"


def _parse_characters(media: dict) -> str:
    """取按 ROLE 排序的前 N 个角色，日文名优先。"""
    nodes = (media.get("characters") or {}).get("nodes") or []
    names = []
    for node in nodes[:MAX_CHARACTERS]:
        name = node.get("name") or {}
        full = name.get("native") or name.get("full")
        if full:
            names.append(full)
    return "、".join(names) or "暂无"


def _parse_studios(media: dict) -> str:
    """取主制作公司，多个用顿号连接。"""
    nodes = (media.get("studios") or {}).get("nodes") or []
    names = [n["name"] for n in nodes if n.get("name")]
    return "、".join(names) or "未知"


def _format_start_date(start_date: dict | None) -> str:
    """格式化首播日期。

    注意 AniList 会把未知的 month / day 返回成 JSON null（键存在但值为 None），
    所以不能用 dict.get 的默认值兜底，必须显式判空，否则 f"{None:02d}" 会抛 TypeError。
    """
    start_date = start_date or {}
    year = start_date.get("year")
    if not year:
        return "未知"
    month = start_date.get("month")
    day = start_date.get("day")
    return f"{year}-{month:02d}-{day:02d}" if month and day else (
        f"{year}-{month:02d}-?" if month else f"{year}-?-?"
    )


def format_entry(media: dict, label: str) -> dict | None:
    """把一条 AniList media 记录转成本项目的输出格式。

    关键字段缺失、或属于成人内容时返回 None，由调用方过滤掉，避免脏数据写入 JSON。
    """
    if not media or not media.get("title"):
        warn("跳过一条缺少 title 的记录")
        return None

    # 查询层已用 isAdult: false 过滤，这里做输出端二次确认
    if media.get("isAdult"):
        warn("跳过一条被判定为成人内容的记录")
        return None

    name, name_en = _parse_title(media.get("title"))

    return {
        "name": name,
        "name_en": name_en,
        "date": label,
        "start_date": _format_start_date(media.get("startDate")),
        "tag": _parse_tags(media),
        "character": _parse_characters(media),
        "author": _parse_studios(media),
        "episodes": media.get("episodes"),
        "status": media.get("status"),
        "score": media.get("averageScore"),
    }


REQUIRED_FIELDS = ("name", "date", "start_date", "status")


def validate_anime_list(anime_list: list[dict]) -> list[str]:
    """写入前的轻量自检，返回错误描述列表；空列表表示校验通过。"""
    if not anime_list:
        return ["抓取结果为空，拒绝写入（避免覆盖成一份空数据）"]

    errors = []
    for index, item in enumerate(anime_list, 1):
        missing = [key for key in REQUIRED_FIELDS if not item.get(key)]
        if missing:
            errors.append(f"第 {index} 条「{item.get('name') or '?'}」字段缺失或为空：{missing}")
            if len(errors) >= 5:
                errors.append("……仅列出前 5 条")
                break
    return errors


def is_last_day_of_month() -> bool:
    """判断今天是否是当月最后一天（用于本地运行时的自动跳过）。"""
    today = datetime.date.today()
    last = calendar.monthrange(today.year, today.month)[1]
    return today.day == last


def resolve_target(today: datetime.date) -> tuple[int, int]:
    """确定要抓取的目标 (年, 月)。

    优先读环境变量 FORCE_MONTH / FORCE_YEAR；只给了月份没给年份时，
    按「离今天最近的那个同名月份」推断年份，避免 1 月补拉 12 月时错误取成今年。
    """
    force_month = os.environ.get("FORCE_MONTH")
    force_year = os.environ.get("FORCE_YEAR")

    if not force_month:
        return today.year, today.month

    month = int(force_month)
    if not 1 <= month <= 12:
        raise ValueError(f"FORCE_MONTH 必须是 1-12 的整数，收到 {force_month!r}")
    if force_year:
        return int(force_year), month

    year = today.year if month <= today.month else today.year - 1
    return year, month


def write_json(path: str, payload: dict) -> None:
    """把结果写为 UTF-8 JSON（保留中文原样）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_summary(label: str, anime_list: list[dict], today: datetime.date) -> None:
    """生成供邮件正文使用的纯文本摘要，含本次抓取状态。"""
    lines = [
        f"📺 {label} 新番月报",
        f"共收录 {len(anime_list)} 部作品",
        f"生成时间：{today}",
        "",
    ]
    if WARNINGS:
        lines += [f"⚠️ 本次抓取有 {len(WARNINGS)} 条告警："]
        lines += [f"- {w}" for w in WARNINGS]
        lines.append("")

    for i, a in enumerate(anime_list[:25], 1):
        lines += [
            f"{i}. 【{a['name']}】 {a['name_en']}",
            f"   标签：{a['tag']}",
            f"   制作：{a['author']}",
            f"   集数：{a['episodes'] or '未知'} | 评分：{a['score'] or '暂无'}",
            "",
        ]
    with open("summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("📝 摘要已写入 summary.txt")


def main() -> int:
    """入口：抓取 → 校验 → 写入 data.json 与归档。返回进程退出码。"""
    today = datetime.date.today()

    # 检查是否月末（CI 内由 workflow 判断，FORCE_MONTH / FORCE_RUN 可强制运行）
    in_ci = bool(os.environ.get("GITHUB_ACTIONS"))
    force = bool(os.environ.get("FORCE_MONTH") or os.environ.get("FORCE_RUN"))

    if not in_ci and not force and not is_last_day_of_month():
        print(f"今天是 {today}，不是月末，跳过。如需强制运行请设置 FORCE_RUN=1")
        return 0

    year, month = resolve_target(today)
    season = month_to_season(month)
    label = season_label(season, year, month)

    print(f"📡 正在抓取 {label} ({season} {year})...")
    raw = fetch_season(season, year)
    print(f"   共获取 {len(raw)} 条原始数据")

    anime_list = [entry for entry in (format_entry(m, label) for m in raw) if entry]
    if len(anime_list) < len(raw):
        print(f"   过滤掉 {len(raw) - len(anime_list)} 条无效记录")

    errors = validate_anime_list(anime_list)
    if errors:
        for problem in errors:
            warn(problem)
        print("[ERROR] 数据校验未通过，放弃写入以避免污染站点数据", file=sys.stderr)
        return 1

    output = {
        "generated_at": today.isoformat(),
        "month": f"{year}-{month:02d}",
        "season": label,
        "season_en": f"{season} {year}",
        "total": len(anime_list),
        "warnings": WARNINGS,
        "anime": anime_list,
    }

    # docs/data.json —— GitHub Pages 入口
    write_json(os.path.join("docs", "data.json"), output)
    print("✅ 已写入 docs/data.json")

    # 归档到 docs/history/YYYY-MM.json
    archive_path = os.path.join("docs", "history", f"{year}-{month:02d}.json")
    write_json(archive_path, output)
    print(f"📦 已归档至 {archive_path}")

    write_summary(label, anime_list, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
