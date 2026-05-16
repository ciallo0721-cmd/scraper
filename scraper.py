"""
scraper.py
每月末自动从 AniList GraphQL API 爬取当季新番信息
输出到 docs/data.json 和 docs/history/YYYY-MM.json
"""

import requests
import json
import os
import datetime
import calendar
import sys

ANILIST_URL = "https://graphql.anilist.co"

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
      characters(sort: ROLE, perPage: 8) {
        nodes { name { full native } }
      }
      studios(isMain: true) {
        nodes { name }
      }
      startDate { year month day }
      episodes
      status
      averageScore
      popularity
    }
  }
}
"""


def month_to_season(month: int) -> str:
    if month in (1, 2, 3):
        return "WINTER"
    elif month in (4, 5, 6):
        return "SPRING"
    elif month in (7, 8, 9):
        return "SUMMER"
    else:
        return "FALL"


def season_label(season: str, year: int, month: int) -> str:
    return f"{year}年{month}月 {SEASON_CN.get(season, season)}"


def fetch_season(season: str, year: int) -> list:
    """分页拉取 AniList 季度动画，最多 3 页（150 条）"""
    results = []
    for page in range(1, 4):
        try:
            resp = requests.post(
                ANILIST_URL,
                json={"query": GRAPHQL_QUERY, "variables": {"season": season, "year": year, "page": page}},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
            body = resp.json()
            page_data = body["data"]["Page"]
            results.extend(page_data["media"])
            if not page_data["pageInfo"]["hasNextPage"]:
                break
        except Exception as e:
            print(f"[WARN] Page {page} fetch error: {e}", file=sys.stderr)
            break
    return results


def format_entry(media: dict, label: str) -> dict:
    # 名称
    name = media["title"].get("native") or media["title"].get("romaji") or "未知"
    name_en = media["title"].get("english") or media["title"].get("romaji") or ""

    # 标签：genres + rank>=60 的 tag，去掉剧透 tag
    genres = media.get("genres") or []
    raw_tags = media.get("tags") or []
    extra_tags = [
        t["name"] for t in raw_tags
        if t.get("rank", 0) >= 60 and not t.get("isMediaSpoiler", False)
    ][:5]
    tag_str = "、".join((genres + extra_tags)[:8]) or "未分类"

    # 角色（取日文名优先）
    nodes = (media.get("characters") or {}).get("nodes") or []
    char_names = []
    for c in nodes[:6]:
        n = c["name"]
        char_names.append(n.get("native") or n.get("full") or "")
    character_str = "、".join(filter(None, char_names)) or "暂无"

    # 制作公司
    studio_nodes = (media.get("studios") or {}).get("nodes") or []
    author_str = "、".join(s["name"] for s in studio_nodes) or "未知"

    # 首播日期
    sd = media.get("startDate") or {}
    start = (
        f"{sd.get('year')}-{sd.get('month', '?'):02}-{sd.get('day', '?'):02}"
        if sd.get("year")
        else "未知"
    )

    return {
        "name": name,
        "name_en": name_en,
        "date": label,
        "start_date": start,
        "tag": tag_str,
        "character": character_str,
        "author": author_str,
        "episodes": media.get("episodes"),
        "status": media.get("status"),
        "score": media.get("averageScore"),
    }


def is_last_day_of_month() -> bool:
    today = datetime.date.today()
    last = calendar.monthrange(today.year, today.month)[1]
    return today.day == last


def resolve_target(today: datetime.date):
    """根据环境变量或当前日期确定要爬取的目标月份"""
    force_month = os.environ.get("FORCE_MONTH")
    force_year  = os.environ.get("FORCE_YEAR")

    if force_month:
        m = int(force_month)
        y = int(force_year) if force_year else today.year
        return y, m

    # 默认：爬当前月份（在月末或 CI 中运行）
    return today.year, today.month


def main():
    today = datetime.date.today()

    # 检查是否月末（workflow_dispatch 或 FORCE_RUN 可跳过此检查）
    in_ci = bool(os.environ.get("GITHUB_ACTIONS"))
    force = bool(os.environ.get("FORCE_MONTH") or os.environ.get("FORCE_RUN"))

    if not in_ci and not force and not is_last_day_of_month():
        print(f"今天是 {today}，不是月末，跳过。如需强制运行请设置 FORCE_RUN=1")
        return

    year, month = resolve_target(today)
    season = month_to_season(month)
    label  = season_label(season, year, month)

    print(f"📡 正在抓取 {label} ({season} {year})...")
    raw = fetch_season(season, year)
    print(f"   共获取 {len(raw)} 条原始数据")

    anime_list = [format_entry(m, label) for m in raw]

    output = {
        "generated_at": today.isoformat(),
        "season": label,
        "season_en": f"{season} {year}",
        "total": len(anime_list),
        "anime": anime_list,
    }

    # 写入 docs/data.json（GitHub Pages 入口）
    os.makedirs("docs", exist_ok=True)
    data_path = os.path.join("docs", "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已写入 {data_path}")

    # 归档
    archive_dir = os.path.join("docs", "history")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{year}-{month:02d}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"📦 已归档至 {archive_path}")

    # 生成邮件摘要文本
    lines = [
        f"📺 {label} 新番月报",
        f"共收录 {len(anime_list)} 部作品",
        f"生成时间：{today}",
        "",
    ]
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


if __name__ == "__main__":
    main()
