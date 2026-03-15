"""Generate a basic daily markdown intelligence report from SQLite."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db


def _fetch_rows(db_path: str, since_iso: str):
    conn = connect(db_path)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT
            a.handle,
            p.created_at,
            p.post_type,
            p.text,
            p.url,
            p.like_count,
            p.repost_count,
            p.reply_count,
            (p.like_count + p.repost_count + p.reply_count + p.quote_count) AS engagement
        FROM posts p
        JOIN accounts a ON a.id = p.account_id
        WHERE p.created_at >= ?
        ORDER BY engagement DESC, p.created_at DESC
        """,
        (since_iso,),
    ).fetchall()
    conn.close()
    return rows


def generate_report(db_path: str, out_path: str, hours: int) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = _fetch_rows(db_path, since.isoformat())

    by_type = defaultdict(list)
    by_handle = defaultdict(int)
    for row in rows:
        by_type[row[2]].append(row)
        by_handle[row[0]] += 1

    lines = []
    lines.append("# Daily Geopolitical & Macro Intelligence Report")
    lines.append("")
    lines.append(f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Lookback window: last {hours} hours")
    lines.append(f"- Total captured items: {len(rows)}")
    lines.append("")

    lines.append("## Coverage Summary")
    lines.append(f"- Posts: {len(by_type['post'])}")
    lines.append(f"- Replies: {len(by_type['reply'])}")
    lines.append(f"- Reposts: {len(by_type['repost'])}")
    lines.append("")

    lines.append("## Most Active Accounts")
    for handle, count in sorted(by_handle.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"- @{handle}: {count} items")
    if not by_handle:
        lines.append("- No activity in this window.")
    lines.append("")

    lines.append("## Highest-Engagement Items")
    for r in rows[:20]:
        handle, created_at, post_type, text, url, likes, reposts, replies, engagement = r
        text_short = (text or "").replace("\n", " ")
        if len(text_short) > 220:
            text_short = text_short[:217] + "..."
        lines.append(
            f"- [{created_at}] @{handle} ({post_type}, engagement={engagement}, ❤️{likes}/🔁{reposts}/💬{replies})"
        )
        lines.append(f"  - {text_short}")
        if url:
            lines.append(f"  - {url}")
    if not rows:
        lines.append("- No captured items for the selected window.")
    lines.append("")

    lines.append("## Quick Analyst Notes")
    lines.append("- Watch for repeated mention clusters across independent handles.")
    lines.append("- Compare maritime mentions with oil price action for lagged transmission.")
    lines.append("- Flag Taiwan-related military tempo changes as potential semis risk catalysts.")

    output = "\n".join(lines) + "\n"
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(output, encoding="utf-8")
    return str(out_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate markdown intelligence report")
    parser.add_argument("--db", default="data/intel.db")
    parser.add_argument("--out", default="reports/daily_report.md")
    parser.add_argument("--hours", type=int, default=24)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    path = generate_report(db_path=args.db, out_path=args.out, hours=args.hours)
    print(f"Report written: {path}")


if __name__ == "__main__":
    main()
