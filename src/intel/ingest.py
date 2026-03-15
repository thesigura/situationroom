"""Ingest posts/replies/reposts from watchlist accounts into SQLite."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .db import connect, init_db, insert_post, upsert_account
from .watchlist import WATCHLIST, WatchAccount


def _detect_post_type(tweet) -> str:
    if getattr(tweet, "retweetedTweet", None) is not None:
        return "repost"
    if getattr(tweet, "inReplyToTweetId", None) is not None:
        return "reply"
    return "post"


def _to_record(tweet, account_id: int) -> dict:
    return {
        "id": str(tweet.id),
        "account_id": account_id,
        "created_at": tweet.date.replace(tzinfo=timezone.utc).isoformat(),
        "post_type": _detect_post_type(tweet),
        "text": tweet.rawContent or "",
        "url": tweet.url,
        "like_count": int(getattr(tweet, "likeCount", 0) or 0),
        "repost_count": int(getattr(tweet, "retweetCount", 0) or 0),
        "reply_count": int(getattr(tweet, "replyCount", 0) or 0),
        "quote_count": int(getattr(tweet, "quoteCount", 0) or 0),
        "lang": getattr(tweet, "lang", None),
        "raw_json": json.dumps(getattr(tweet, "__dict__", {}), default=str),
    }


def _iter_snscrape(account: WatchAccount, since_utc: datetime, limit: int):
    try:
        import snscrape.modules.twitter as sntwitter
    except ModuleNotFoundError as exc:
        raise RuntimeError("snscrape is required for source=snscrape") from exc

    query = f"from:{account.handle} since:{since_utc.date().isoformat()}"
    scraper = sntwitter.TwitterSearchScraper(query)
    count = 0
    for tweet in scraper.get_items():
        tdate = tweet.date if tweet.date.tzinfo else tweet.date.replace(tzinfo=timezone.utc)
        if tdate < since_utc:
            continue
        yield tweet
        count += 1
        if count >= limit:
            break


def _iter_mock(account: WatchAccount):
    """Deterministic local test data to validate pipeline without network access."""

    class T:
        pass

    now = datetime.now(timezone.utc)
    items = [
        {
            "id": f"{account.handle}-p1",
            "date": now - timedelta(hours=2),
            "rawContent": f"{account.handle}: Strait tension rising near key chokepoint.",
            "url": f"https://x.com/{account.handle}/status/1",
            "likeCount": 42,
            "retweetCount": 19,
            "replyCount": 11,
            "quoteCount": 3,
            "lang": "en",
            "retweetedTweet": None,
            "inReplyToTweetId": None,
        },
        {
            "id": f"{account.handle}-r1",
            "date": now - timedelta(hours=1, minutes=10),
            "rawContent": f"{account.handle}: Reply discussing tanker insurance repricing.",
            "url": f"https://x.com/{account.handle}/status/2",
            "likeCount": 17,
            "retweetCount": 4,
            "replyCount": 7,
            "quoteCount": 0,
            "lang": "en",
            "retweetedTweet": None,
            "inReplyToTweetId": 12345,
        },
        {
            "id": f"{account.handle}-rp1",
            "date": now - timedelta(minutes=30),
            "rawContent": f"{account.handle}: Reposting report on port delays.",
            "url": f"https://x.com/{account.handle}/status/3",
            "likeCount": 9,
            "retweetCount": 8,
            "replyCount": 2,
            "quoteCount": 1,
            "lang": "en",
            "retweetedTweet": {"id": "orig-1"},
            "inReplyToTweetId": None,
        },
    ]
    for item in items:
        tweet = T()
        for k, v in item.items():
            setattr(tweet, k, v)
        yield tweet


def ingest(db_path: str, source: str, lookback_hours: int, limit_per_account: int) -> tuple[int, int]:
    conn = connect(db_path)
    init_db(conn)

    since_utc = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    total_accounts = 0
    total_posts = 0

    for account in WATCHLIST:
        total_accounts += 1
        account_id = upsert_account(conn, account.handle, account.category, account.priority)

        if source == "snscrape":
            iterator = _iter_snscrape(account, since_utc=since_utc, limit=limit_per_account)
        else:
            iterator = _iter_mock(account)

        for tweet in iterator:
            record = _to_record(tweet, account_id)
            insert_post(conn, record)
            total_posts += 1

    conn.commit()
    conn.close()
    return total_accounts, total_posts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest watchlist content into SQLite")
    parser.add_argument("--db", default="data/intel.db", help="SQLite path")
    parser.add_argument(
        "--source",
        choices=["mock", "snscrape"],
        default="mock",
        help="mock for local testing, snscrape for live public data",
    )
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit-per-account", type=int, default=100)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    accounts, posts = ingest(
        db_path=args.db,
        source=args.source,
        lookback_hours=args.lookback_hours,
        limit_per_account=args.limit_per_account,
    )
    print(f"Ingestion complete: accounts={accounts} posts={posts} db={args.db}")


if __name__ == "__main__":
    main()
