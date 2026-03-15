"""Generate static HTML previews for Situation Room pages from SQLite data."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


BG = "#0b1020"
CARD = "#121a33"
BORDER = "#28345f"
MUTED = "#9fb0e8"
TEXT = "#e7ecff"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _styles() -> str:
    return f"""
  <style>
    body {{ font-family: Inter, Arial, sans-serif; background:{BG}; color:{TEXT}; margin:0; padding:24px; }}
    .wrap {{ max-width:1240px; margin:0 auto; }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }}
    .card {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px; padding:14px; }}
    .label {{ color:{MUTED}; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .value {{ font-size:28px; font-weight:700; margin-top:6px; }}
    .panel {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px; padding:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ border-bottom:1px solid {BORDER}; padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:{MUTED}; font-weight:600; }}
    h1 {{ margin:0 0 6px; }}
    .sub {{ color:{MUTED}; margin-bottom:16px; }}
    .tabs {{ display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }}
    .tab {{ padding:8px 10px; border:1px solid {BORDER}; border-radius:9px; background:{CARD}; color:{MUTED}; text-decoration:none; }}
    .tab.active {{ color:{TEXT}; border-color:#4f67b0; }}
  </style>
"""


def _layout(title: str, subtitle: str, active_page: str, body_html: str) -> str:
    tabs = [
        ("index.html", "Overview", "overview"),
        ("live_feed.html", "Live Feed", "live_feed"),
        ("account_activity.html", "Account Activity", "account_activity"),
        ("crawler_health.html", "Crawler Health", "crawler_health"),
        ("report_preview.html", "Report Preview", "report_preview"),
    ]
    nav = "".join(
        f'<a class="tab {"active" if key == active_page else ""}" href="{href}">{label}</a>'
        for href, label, key in tabs
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{escape(title)}</title>
{_styles()}
</head>
<body>
<div class=\"wrap\">
  <h1>🌐 {escape(title)}</h1>
  <div class=\"sub\">{escape(subtitle)}</div>
  <div class=\"tabs\">{nav}</div>
  {body_html}
</div>
</body>
</html>
"""


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    if rows:
        body = "\n".join(
            "<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
        )
    else:
        body = f'<tr><td colspan="{len(headers)}">No data available.</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def generate_previews(db_path: str, out_dir: str, hours: int, limit: int = 30) -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    generated_ts = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)

    kpis = {
        "watched_accounts": _scalar(conn, "SELECT COUNT(*) FROM accounts"),
        "captured_items": _scalar(conn, "SELECT COUNT(*) FROM posts WHERE created_at >= ?", (since,)),
        "active_accounts": _scalar(conn, "SELECT COUNT(DISTINCT account_id) FROM posts WHERE created_at >= ?", (since,)),
        "crawler_errors_24h": _scalar(conn, "SELECT COUNT(*) FROM crawl_errors WHERE created_at >= datetime('now', '-1 day')"),
    }

    kpi_html = f"""
  <section class=\"kpis\">
    <div class=\"card\"><div class=\"label\">Watched accounts</div><div class=\"value\">{kpis['watched_accounts']}</div></div>
    <div class=\"card\"><div class=\"label\">Captured items</div><div class=\"value\">{kpis['captured_items']}</div></div>
    <div class=\"card\"><div class=\"label\">Active accounts</div><div class=\"value\">{kpis['active_accounts']}</div></div>
    <div class=\"card\"><div class=\"label\">Crawler errors (24h)</div><div class=\"value\">{kpis['crawler_errors_24h']}</div></div>
  </section>
"""

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
    feed_rows = [[f"@{r['handle']}", r["created_at"], r["post_type"], (r["text"] or "")[:180], r["engagement"]] for r in feed]

    activity = _rows(
        conn,
        """
        SELECT a.handle, a.category, a.priority,
               COUNT(p.id) AS items,
               SUM(CASE WHEN p.post_type='post' THEN 1 ELSE 0 END) AS posts,
               SUM(CASE WHEN p.post_type='reply' THEN 1 ELSE 0 END) AS replies,
               SUM(CASE WHEN p.post_type='repost' THEN 1 ELSE 0 END) AS reposts,
               MAX(p.created_at) AS last_seen
        FROM accounts a
        LEFT JOIN posts p ON p.account_id = a.id AND p.created_at >= ?
        GROUP BY a.id, a.handle, a.category, a.priority
        ORDER BY items DESC, a.priority ASC, a.handle ASC
        """,
        (since,),
    )
    activity_rows = [
        [f"@{r['handle']}", r["category"], r["priority"], r["items"], r["posts"], r["replies"], r["reposts"], r["last_seen"] or "-"]
        for r in activity
    ]

    state = _rows(
        conn,
        """
        SELECT cs.source, a.handle, cs.last_seen_created_at, cs.last_seen_post_id, cs.updated_at
        FROM crawl_state cs JOIN accounts a ON a.id = cs.account_id
        ORDER BY cs.updated_at DESC
        LIMIT 100
        """,
    )
    state_rows = [[r["source"], f"@{r['handle']}", r["last_seen_created_at"], r["last_seen_post_id"], r["updated_at"]] for r in state]

    errors = _rows(
        conn,
        """
        SELECT created_at, source, account_handle, error
        FROM crawl_errors
        ORDER BY created_at DESC
        LIMIT 100
        """,
    )
    error_rows = [[r["created_at"], r["source"], f"@{r['account_handle'] or '-'}", r["error"]] for r in errors]

    report_rows = sorted(feed_rows, key=lambda x: int(x[4]), reverse=True)[:15]
    conn.close()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    pages = {
        "index.html": _layout(
            "Situation Room Preview",
            f"Generated {generated_ts} • Lookback: last {hours}h",
            "overview",
            kpi_html + '<section class="panel"><h2 style="margin-top:0">Overview</h2><p>Use the tabs above to inspect each page preview.</p></section>',
        ),
        "live_feed.html": _layout(
            "Situation Room — Live Feed",
            f"Generated {generated_ts} • Last {hours}h • Top {limit}",
            "live_feed",
            kpi_html + '<section class="panel"><h2 style="margin-top:0">Live Feed</h2>' + _render_table(["Handle", "Time (UTC)", "Type", "Text", "Engagement"], feed_rows) + "</section>",
        ),
        "account_activity.html": _layout(
            "Situation Room — Account Activity",
            f"Generated {generated_ts} • Last {hours}h",
            "account_activity",
            kpi_html + '<section class="panel"><h2 style="margin-top:0">Account Activity</h2>' + _render_table(["Handle", "Category", "Priority", "Items", "Posts", "Replies", "Reposts", "Last Seen"], activity_rows) + "</section>",
        ),
        "crawler_health.html": _layout(
            "Situation Room — Crawler Health",
            f"Generated {generated_ts}",
            "crawler_health",
            kpi_html
            + '<section class="panel"><h2 style="margin-top:0">Checkpoint State</h2>'
            + _render_table(["Source", "Handle", "Last Seen", "Last Post ID", "Updated At"], state_rows)
            + "</section><br/>"
            + '<section class="panel"><h2 style="margin-top:0">Recent Errors</h2>'
            + _render_table(["Created At", "Source", "Handle", "Error"], error_rows)
            + "</section>",
        ),
        "report_preview.html": _layout(
            "Situation Room — Report Preview",
            f"Generated {generated_ts} • Ranked by engagement",
            "report_preview",
            kpi_html + '<section class="panel"><h2 style="margin-top:0">Top Report Candidates</h2>' + _render_table(["Handle", "Time (UTC)", "Type", "Text", "Engagement"], report_rows) + "</section>",
        ),
    }

    paths = []
    for filename, html in pages.items():
        p = out / filename
        p.write_text(html, encoding="utf-8")
        paths.append(str(p))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static Situation Room page previews")
    parser.add_argument("--db", default="data/intel.db")
    parser.add_argument("--out-dir", default="preview")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    paths = generate_previews(db_path=args.db, out_dir=args.out_dir, hours=args.hours, limit=args.limit)
    print("Preview pages written:")
    for p in paths:
        print(f"- {p}")


if __name__ == "__main__":
    main()
