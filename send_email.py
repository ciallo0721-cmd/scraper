"""
send_email.py
读取 scraper.py 生成的 summary.txt / docs/data.json
通过 QQ 邮箱 SMTP 发送 HTML 月报邮件

所需环境变量（在 GitHub Secrets 中配置）：
  SMTP_USER  — 发件人 QQ 邮箱，如 3627742771@qq.com
  SMTP_PASS  — QQ 邮箱授权码（非登录密码）
  TO_EMAIL   — 收件人邮箱（可与 SMTP_USER 相同）
  SITE_URL   — 可选，站点地址，用于邮件里的数据直链

退出码：0 = 成功或主动跳过；1 = 读取数据 / 发送失败（工作流会标红提醒）
"""

from __future__ import annotations

import datetime
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

HISTORY_DIR = os.path.join("docs", "history")
DEFAULT_SITE_URL = "https://ciallo0721-cmd.github.io/scraper"
MAX_NAME_PREVIEW = 12   # 增减明细里最多列几个名字


def load_data(path: str = os.path.join("docs", "data.json")) -> dict:
    """读取本次抓取结果。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_previous_month(month_key: str) -> dict | None:
    """读取上一次归档（文件名小于 month_key 里最新的那份），找不到就返回 None。"""
    try:
        names = sorted(n[:-5] for n in os.listdir(HISTORY_DIR) if n.endswith(".json"))
    except OSError:
        return None

    older = [n for n in names if n < month_key]
    if not older:
        return None
    try:
        with open(os.path.join(HISTORY_DIR, f"{older[-1]}.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def diff_names(current: list[dict], previous: dict | None) -> tuple[list[str], list[str]]:
    """按作品名对比出（新增, 移除）。"""
    if not previous:
        return [], []
    cur = {a.get("name") for a in current if a.get("name")}
    old = {a.get("name") for a in previous.get("anime", []) if a.get("name")}
    return sorted(cur - old), sorted(old - cur)


def _name_list(names: list[str]) -> str:
    """把名字列表拼成可读的一行，过长时截断。"""
    text = "、".join(escape(n) for n in names[:MAX_NAME_PREVIEW])
    return text + ("…" if len(names) > MAX_NAME_PREVIEW else "")


def build_notice(previous: dict | None, added: list[str], removed: list[str],
                 warnings: list[str]) -> str:
    """生成邮件正文顶部的状态块：增减对比 + 抓取告警。"""
    blocks: list[str] = []

    if previous:
        parts = [
            f"较上期（{escape(str(previous.get('season', '上期')))}，{previous.get('total', 0)} 部）",
            f"新增 <b style='color:#2e7d32'>{len(added)}</b> 部",
            f"移除 <b style='color:#c62828'>{len(removed)}</b> 部",
        ]
        detail = ""
        if added:
            detail += (f"<p style='margin:8px 0 0;color:#2e7d32;font-size:12px'>"
                       f"＋ {_name_list(added)}</p>")
        if removed:
            detail += (f"<p style='margin:4px 0 0;color:#c62828;font-size:12px'>"
                       f"－ {_name_list(removed)}</p>")
        blocks.append(
            "<div style='background:#f1f8ff;border-left:4px solid #1a73e8;padding:12px 16px;"
            "border-radius:6px;margin-bottom:14px;font-size:13px;color:#20344d'>"
            f"<p style='margin:0'>{' · '.join(parts)}</p>{detail}</div>"
        )

    if warnings:
        items = "".join(f"<li>{escape(str(w))}</li>" for w in warnings)
        blocks.append(
            "<div style='background:#fff8e1;border-left:4px solid #ffb300;padding:12px 16px;"
            "border-radius:6px;margin-bottom:14px'>"
            f"<p style='margin:0 0 6px;font-weight:bold;color:#8d6e00'>"
            f"⚠️ 本次抓取有 {len(warnings)} 条告警</p>"
            f"<ul style='margin:0;padding-left:20px;color:#6d5a00;font-size:13px'>{items}</ul>"
            "</div>"
        )

    return "".join(blocks)


def build_links(month_key: str) -> str:
    """生成数据文件直链，方便收到邮件后直接核对。"""
    if not month_key:
        return ""
    base = os.environ.get("SITE_URL", DEFAULT_SITE_URL).rstrip("/")
    style = "color:#1a73e8;text-decoration:none"
    return (
        "<div style='padding:0 36px 20px;font-size:12px;color:#888'>"
        f"数据文件：<a href='{base}/data.json' style='{style}'>data.json</a>"
        f" · <a href='{base}/history/{escape(month_key)}.json' style='{style}'>"
        f"history/{escape(month_key)}.json</a></div>"
    )


def build_html(data: dict, previous: dict | None = None) -> str:
    """渲染 HTML 邮件正文。"""
    anime_list = data.get("anime", [])
    season = escape(str(data.get("season", "新番月报")))
    total = data.get("total", 0)
    gen_at = escape(str(data.get("generated_at", "")))
    month_key = str(data.get("month") or "")
    warnings = data.get("warnings") or []

    added, removed = diff_names(anime_list, previous)
    notice = build_notice(previous, added, removed, warnings)
    links = build_links(month_key)

    rows = ""
    for i, a in enumerate(anime_list[:50], 1):
        score = a.get("score")
        score_text = f"{score}分" if score else "暂无"
        score_color = "#e53935" if score and score >= 75 else "#888"
        ep_text = f"{a.get('episodes')}集" if a.get("episodes") else "未知"
        rows += (
            f"<tr style='background:{'#fff' if i % 2 else '#fafafa'}'>"
            f"<td style='padding:8px 12px;font-weight:bold'>{escape(str(a.get('name', '')))}</td>"
            f"<td style='padding:8px 12px;color:#666;font-size:13px'>"
            f"{escape(str(a.get('name_en', '')))}</td>"
            f"<td style='padding:8px 12px;color:#444;font-size:13px'>"
            f"{escape(str(a.get('tag', '')))}</td>"
            f"<td style='padding:8px 12px;font-size:13px'>"
            f"{escape(str(a.get('author', '')))}</td>"
            f"<td style='padding:8px 12px;color:#888;font-size:13px;white-space:nowrap'>"
            f"{ep_text}</td>"
            f"<td style='padding:8px 12px;color:{score_color};font-weight:bold;"
            f"white-space:nowrap'>{score_text}</td>"
            "</tr>"
        )

    more_hint = (
        "<p style='color:#999;font-size:12px;margin-top:16px'>"
        "仅展示前 50 部，完整数据请访问站点</p>"
        if total > 50 else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>{season}</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'PingFang SC',sans-serif">
  <div style="max-width:900px;margin:30px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);padding:32px 36px;color:#fff">
      <h1 style="margin:0 0 8px;font-size:26px">📺 {season}</h1>
      <p style="margin:0;opacity:.85">共收录 <strong>{total}</strong> 部作品 · 数据来源 AniList · {gen_at}</p>
    </div>
    <div style="padding:24px 36px">
      {notice}
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#e8f0fe">
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">名称</th>
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">英文名</th>
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">标签题材</th>
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">制作公司</th>
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">集数</th>
            <th style="padding:10px 12px;text-align:left;color:#1a73e8">评分</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      {more_hint}
    </div>
    {links}
    <div style="padding:16px 36px;background:#f8f9fa;border-top:1px solid #eee;color:#999;font-size:12px">
      由 GitHub Actions 自动生成 · ciallo0721-cmd/scraper
    </div>
  </div>
</body>
</html>"""


def send_email() -> int:
    """发送月报邮件，返回进程退出码。"""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email = os.environ.get("TO_EMAIL") or smtp_user

    if not smtp_user or not smtp_pass:
        print("[SKIP] 未配置 SMTP_USER / SMTP_PASS，跳过邮件发送")
        return 0

    # 读取本次数据
    try:
        data = load_data()
    except FileNotFoundError:
        print("[ERROR] docs/data.json 不存在，请先运行 scraper.py", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[ERROR] docs/data.json 解析失败：{exc}", file=sys.stderr)
        return 1

    season_label = data.get("season", "新番月报")

    # 读取上期归档用于对比（缺失时降级为不显示对比）
    previous = load_previous_month(str(data.get("month") or ""))

    try:
        with open("summary.txt", encoding="utf-8") as f:
            plain_text = f.read()
    except OSError:
        plain_text = season_label

    subject = f"📺 {season_label} — 新番月报 {datetime.date.today().isoformat()}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(build_html(data, previous), "html", "utf-8"))

    print(f"📧 正在发送邮件到 {to_email} ...")
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
    except Exception as exc:
        print(f"[ERROR] 邮件发送失败：{exc}", file=sys.stderr)
        return 1

    print("✅ 邮件发送成功")
    return 0


if __name__ == "__main__":
    sys.exit(send_email())
