"""Ingest posts/replies/reposts from watchlist accounts into SQLite."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .db import (
    connect,
    get_last_seen_created_at,
    init_db,
    insert_crawl_error,
    insert_post,
    upsert_account,
    upsert_crawl_state,
)
from .watchlist import WATCHLIST, WatchAccount


def _detect_post_type(tweet) -> str:
    if getattr(tweet, "retweetedTweet", None) is not None:
        return "repost"
    if getattr(tweet, "inReplyToTweetId", None) is not None:
        return "reply"
    return "post"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_x_time(value: str) -> datetime:
    # Example: 2024-01-01T12:34:56.000Z
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _to_record(tweet, account_id: int) -> dict:
    created_at = _to_utc(tweet.date)
    return {
        "id": str(tweet.id),
        "account_id": account_id,
        "created_at": created_at.isoformat(),
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
        raise RuntimeError(
            "snscrape is required for source=snscrape. Install it in the same interpreter used to run this command: python -m pip install -r requirements.txt"
        ) from exc

    query = f"from:{account.handle} since:{since_utc.date().isoformat()}"
    scraper = sntwitter.TwitterSearchScraper(query)
    count = 0
    for tweet in scraper.get_items():
        tdate = _to_utc(tweet.date)
        if tdate < since_utc:
            continue
        yield tweet
        count += 1
        if count >= limit:
            break


def _x_api_get_json(path: str, token: str, params: dict | None = None) -> dict:
    base = "https://api.twitter.com/2"
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base}{path}{query}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"X API HTTP {exc.code}: {body[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"X API connection error: {exc}") from exc


def _iter_xapi(account: WatchAccount, since_utc: datetime, limit: int):
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise RuntimeError("X_BEARER_TOKEN is required for source=xapi")

    user_payload = _x_api_get_json(
        f"/users/by/username/{account.handle}",
        token,
        params={"user.fields": "id,username"},
    )
    user = user_payload.get("data")
    if not user:
        raise RuntimeError(f"User not found via X API for @{account.handle}")

    user_id = user["id"]
    params = {
        "max_results": min(max(limit, 5), 100),
        "tweet.fields": "created_at,lang,public_metrics,referenced_tweets",
        "exclude": "",
    }
    payload = _x_api_get_json(f"/users/{user_id}/tweets", token, params=params)
    for tw in payload.get("data", []):
        created = _parse_x_time(tw["created_at"])
        if created < since_utc:
            continue

        refs = tw.get("referenced_tweets", [])
        ref_types = {r.get("type") for r in refs}
        retweeted = {"id": "1"} if "retweeted" in ref_types else None
        reply_to = tw["id"] if "replied_to" in ref_types else None
        metrics = tw.get("public_metrics", {})

        yield SimpleNamespace(
            id=tw["id"],
            date=created,
            rawContent=tw.get("text", ""),
            url=f"https://x.com/{account.handle}/status/{tw['id']}",
            likeCount=metrics.get("like_count", 0),
            retweetCount=metrics.get("retweet_count", 0),
            replyCount=metrics.get("reply_count", 0),
            quoteCount=metrics.get("quote_count", 0),
            lang=tw.get("lang"),
            retweetedTweet=retweeted,
            inReplyToTweetId=reply_to,
            raw=tw,
        )


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


def ingest(
    db_path: str,
    source: str,
    lookback_hours: int,
    limit_per_account: int,
    resume_state: bool,
) -> tuple[int, int, int]:
    conn = connect(db_path)
    init_db(conn)

    fallback_since_utc = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    total_accounts = 0
    total_posts = 0
    total_errors = 0

    for account in WATCHLIST:
        total_accounts += 1
        account_id = upsert_account(conn, account.handle, account.category, account.priority)

        since_utc = fallback_since_utc
        if resume_state:
            last_seen = get_last_seen_created_at(conn, source=source, account_id=account_id)
            if last_seen:
                since_utc = datetime.fromisoformat(last_seen)

        try:
            if source == "snscrape":
                iterator = _iter_snscrape(account, since_utc=since_utc, limit=limit_per_account)
            elif source == "xapi":
                iterator = _iter_xapi(account, since_utc=since_utc, limit=limit_per_account)
            else:
                iterator = _iter_mock(account)

            newest_created: datetime | None = None
            newest_post_id: str | None = None

            for tweet in iterator:
                created = _to_utc(tweet.date)
                if resume_state and created <= since_utc:
                    continue
                record = _to_record(tweet, account_id)
                is_new = insert_post(conn, record)
                if is_new:
                    total_posts += 1

                if newest_created is None or created > newest_created:
                    newest_created = created
                    newest_post_id = str(tweet.id)

            if newest_created is not None and newest_post_id is not None:
                upsert_crawl_state(
                    conn,
                    source=source,
                    account_id=account_id,
                    last_seen_created_at=newest_created.isoformat(),
                    last_seen_post_id=newest_post_id,
                )
        except Exception as exc:  # continue other accounts if one fails
            total_errors += 1
            insert_crawl_error(
                conn,
                source=source,
                account_id=account_id,
                account_handle=account.handle,
                error=str(exc),
            )

    conn.commit()
    conn.close()
    return total_accounts, total_posts, total_errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest watchlist content into SQLite")
    parser.add_argument("--db", default="data/intel.db", help="SQLite path")
    parser.add_argument(
        "--source",
        choices=["mock", "snscrape", "xapi"],
        default="mock",
        help="mock for local testing, snscrape for public scraping, xapi for official X API",
    )
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit-per-account", type=int, default=100)
    parser.add_argument(
        "--resume-state",
        action="store_true",
        default=True,
        help="Use crawl_state checkpoints for incremental ingestion (default: enabled)",
    )
    parser.add_argument(
        "--no-resume-state",
        action="store_false",
        dest="resume_state",
        help="Ignore stored checkpoints and use lookback window only",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    accounts, posts, errors = ingest(
        db_path=args.db,
        source=args.source,
        lookback_hours=args.lookback_hours,
        limit_per_account=args.limit_per_account,
        resume_state=args.resume_state,
    )
    print(
        "Ingestion complete: "
        f"accounts={accounts} posts={posts} errors={errors} db={args.db} source={args.source}"
    )


if __name__ == "__main__":
    main()
