"""Situation Room web interface for the intelligence pipeline."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import streamlit as st


st.set_page_config(page_title="Situation Room", page_icon="🌐", layout="wide")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def render() -> None:
    st.title("🌐 Situation Room")
    st.caption("Geopolitical & Macro Market Intelligence Interface")

    with st.sidebar:
        st.header("Settings")
        db_path = st.text_input("SQLite DB path", value="data/intel.db")
        lookback_hours = st.slider("Lookback (hours)", min_value=1, max_value=168, value=24)
        limit = st.slider("Max feed rows", min_value=20, max_value=500, value=100, step=20)

    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()

    try:
        conn = _connect(db_path)
    except sqlite3.Error as exc:
        st.error(f"Could not open database: {exc}")
        return

    total_accounts = _scalar(conn, "SELECT COUNT(*) FROM accounts")
    total_posts = _scalar(conn, "SELECT COUNT(*) FROM posts WHERE created_at >= ?", (since,))
    total_errors = _scalar(conn, "SELECT COUNT(*) FROM crawl_errors WHERE created_at >= datetime('now', '-1 day')")
    distinct_active = _scalar(
        conn,
        "SELECT COUNT(DISTINCT account_id) FROM posts WHERE created_at >= ?",
        (since,),
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Watched accounts", total_accounts)
    c2.metric("Captured items", total_posts)
    c3.metric("Active accounts", distinct_active)
    c4.metric("Crawler errors (24h)", total_errors)

    tabs = st.tabs(["Live Feed", "Account Activity", "Crawler Health", "Report Preview"])

    with tabs[0]:
        st.subheader("Live Feed")
        selected_types = st.multiselect("Include types", ["post", "reply", "repost"], default=["post", "reply", "repost"])
        if selected_types:
            placeholders = ",".join(["?"] * len(selected_types))
            feed = _query(
                conn,
                f"""
                SELECT a.handle, p.created_at, p.post_type, p.text, p.url,
                       p.like_count, p.repost_count, p.reply_count,
                       (p.like_count + p.repost_count + p.reply_count + p.quote_count) AS engagement
                FROM posts p
                JOIN accounts a ON a.id = p.account_id
                WHERE p.created_at >= ? AND p.post_type IN ({placeholders})
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (since, *selected_types, limit),
            )
            st.dataframe(feed, use_container_width=True, hide_index=True)
        else:
            st.info("Pick at least one type to display feed rows.")

    with tabs[1]:
        st.subheader("Account Activity")
        activity = _query(
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
        st.dataframe(activity, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Crawler Health")
        states = _query(
            conn,
            """
            SELECT cs.source, a.handle, cs.last_seen_created_at, cs.last_seen_post_id, cs.updated_at
            FROM crawl_state cs
            JOIN accounts a ON a.id = cs.account_id
            ORDER BY cs.updated_at DESC
            LIMIT 200
            """,
        )
        errors = _query(
            conn,
            """
            SELECT created_at, source, account_handle, error
            FROM crawl_errors
            ORDER BY created_at DESC
            LIMIT 200
            """,
        )
        st.markdown("**Checkpoint state**")
        st.dataframe(states, use_container_width=True, hide_index=True)
        st.markdown("**Recent crawl errors**")
        st.dataframe(errors, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Report Preview")
        top = _query(
            conn,
            """
            SELECT a.handle, p.created_at, p.post_type, p.text,
                   (p.like_count + p.repost_count + p.reply_count + p.quote_count) AS engagement
            FROM posts p JOIN accounts a ON a.id = p.account_id
            WHERE p.created_at >= ?
            ORDER BY engagement DESC, p.created_at DESC
            LIMIT 15
            """,
            (since,),
        )
        st.markdown("These rows are what your daily markdown report prioritizes.")
        st.dataframe(top, use_container_width=True, hide_index=True)

    conn.close()


if __name__ == "__main__":
    render()
