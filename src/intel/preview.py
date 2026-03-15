"""Generate a static HTML preview of the Situation Room from SQLite data."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def generate_preview(db_path: str, out_path: str, hours: int, limit: int = 30) -> str:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = _connect(db_path)

    kpis = {
        "watched_accounts": _scalar(conn, "SELECT COUNT(*) FROM accounts"),
        "captured_items": _scalar(conn, "SELECT COUNT(*) FROM posts WHERE created_at >= ?", (since,)),
        "active_accounts": _scalar(conn, "SELECT COUNT(DISTINCT account_id) FROM posts WHERE created_at >= ?", (since,)),
        "crawler_errors_24h": _scalar(conn, "SELECT COUNT(*) FROM crawl_errors WHERE created_at >= datetime('now', '-1 day')"),
    }

    feed = _rows(
        conn,
        """
        SELECT a.handle, p.created_at, p.post_type, p.text,
               (p.like_count + p.repost_count + p.reply_count + p.quote_count) AS engagement
        FROM posts p JOIN accounts a ON a.id = p.account_id
        WHERE p.created_at >= ?
        ORDER BY p.created_at DESC
        LIMIT ?
        """,
        (since, limit),
    )
    conn.close()

    def r(name: str) -> str:
        return escape(str(kpis[name]))

    rows_html = "\n".join(
        f"<tr><td>@{escape(row['handle'])}</td><td>{escape(row['created_at'])}</td><td>{escape(row['post_type'])}</td><td>{escape((row['text'] or '')[:160])}</td><td>{escape(str(row['engagement']))}</td></tr>"
        for row in feed
    )
    if not rows_html:
        rows_html = '<tr><td colspan="5">No data available in selected lookback window.</td></tr>'

    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Situation Room Preview</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; background:#0b1020; color:#e7ecff; margin:0; padding:24px; }}
    .wrap {{ max-width:1200px; margin:0 auto; }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }}
    .card {{ background:#121a33; border:1px solid #28345f; border-radius:12px; padding:14px; }}
    .label {{ color:#9fb0e8; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .value {{ font-size:28px; font-weight:700; margin-top:6px; }}
    .panel {{ background:#121a33; border:1px solid #28345f; border-radius:12px; padding:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ border-bottom:1px solid #28345f; padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:#9fb0e8; font-weight:600; }}
    h1 {{ margin:0 0 6px; }}
    .sub {{ color:#9fb0e8; margin-bottom:16px; }}
  </style>
</head>
<body>
<div class=\"wrap\">
  <h1>🌐 Situation Room Preview</h1>
  <div class=\"sub\">Generated {escape(datetime.now(timezone.utc).isoformat())} • Lookback: last {hours}h</div>
  <section class=\"kpis\">
    <div class=\"card\"><div class=\"label\">Watched accounts</div><div class=\"value\">{r('watched_accounts')}</div></div>
    <div class=\"card\"><div class=\"label\">Captured items</div><div class=\"value\">{r('captured_items')}</div></div>
    <div class=\"card\"><div class=\"label\">Active accounts</div><div class=\"value\">{r('active_accounts')}</div></div>
    <div class=\"card\"><div class=\"label\">Crawler errors (24h)</div><div class=\"value\">{r('crawler_errors_24h')}</div></div>
  </section>
  <section class=\"panel\">
    <h2 style=\"margin-top:0\">Live Feed (top {limit})</h2>
    <table>
      <thead><tr><th>Handle</th><th>Time (UTC)</th><th>Type</th><th>Text</th><th>Engagement</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </section>
</div>
</body>
</html>
"""

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return str(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static Situation Room HTML preview")
    parser.add_argument("--db", default="data/intel.db")
    parser.add_argument("--out", default="preview/situation_room_preview.html")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    path = generate_preview(db_path=args.db, out_path=args.out, hours=args.hours, limit=args.limit)
    print(f"Preview written: {path}")


if __name__ == "__main__":
    main()
