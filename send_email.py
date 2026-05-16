"""
send_email.py
读取 scraper.py 生成的 summary.txt / docs/data.json
通过 QQ 邮箱 SMTP 发送 HTML 月报邮件

所需环境变量（在 GitHub Secrets 中配置）：
  SMTP_USER  — 发件人 QQ 邮箱，如 3627742771@qq.com
  SMTP_PASS  — QQ 邮箱授权码（非登录密码）
  TO_EMAIL   — 收件人邮箱（可与 SMTP_USER 相同）
"""

import smtplib
import os
import json
import datetime
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def build_html(data: dict) -> str:
    anime_list = data.get("anime", [])
    season     = data.get("season", "新番月报")
    total      = data.get("total", 0)
    gen_at     = data.get("generated_at", "")

    rows = ""
    for i, a in enumerate(anime_list[:50], 1):
        score_text = f"{a.get('score')}分" if a.get("score") else "暂无"
        ep_text    = f"{a.get('episodes')}集" if a.get("episodes") else "未知"
        rows += f"""
        <tr style="background:{'#fff' if i%2 else '#fafafa'}">
          <td style="padding:8px 12px;font-weight:bold;white-space:nowrap">{a.get('name','')}</td>
          <td style="padding:8px 12px;color:#666;font-size:13px">{a.get('name_en','')}</td>
          <td style="padding:8px 12px;color:#444;font-size:13px">{a.get('tag','')}</td>
          <td style="padding:8px 12px;font-size:13px">{a.get('author','')}</td>
          <td style="padding:8px 12px;color:#888;font-size:13px;white-space:nowrap">{ep_text}</td>
          <td style="padding:8px 12px;color:{'#e53935' if a.get('score',0) and a['score']>=75 else '#888'};font-weight:bold;white-space:nowrap">{score_text}</td>
        </tr>"""

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
      {"<p style='color:#999;font-size:12px;margin-top:16px'>仅展示前50部，完整数据请访问 GitHub Pages</p>" if total > 50 else ""}
    </div>
    <div style="padding:16px 36px;background:#f8f9fa;border-top:1px solid #eee;color:#999;font-size:12px">
      由 GitHub Actions 自动生成 · ciallo0721-cmd/scraper
    </div>
  </div>
</body>
</html>"""


def send_email():
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email  = os.environ.get("TO_EMAIL") or smtp_user

    if not smtp_user or not smtp_pass:
        print("[SKIP] 未配置 SMTP_USER / SMTP_PASS，跳过邮件发送")
        return

    # 读取数据
    try:
        with open("docs/data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        season_label = data.get("season", "新番月报")
    except FileNotFoundError:
        print("[ERROR] docs/data.json 不存在，请先运行 scraper.py", file=sys.stderr)
        sys.exit(1)

    try:
        with open("summary.txt", "r", encoding="utf-8") as f:
            plain_text = f.read()
    except FileNotFoundError:
        plain_text = season_label

    subject = f"📺 {season_label} — 新番月报 {datetime.date.today().isoformat()}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_email

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(build_html(data), "html", "utf-8"))

    print(f"📧 正在发送邮件到 {to_email} ...")
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        print("✅ 邮件发送成功")
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    send_email()
