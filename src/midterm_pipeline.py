"""Reusable data and analytics helpers for the 2026 midterm research notebook.

All endpoints are read-only.  Provider credentials are passed through environment
variables so secrets never enter the notebook or repository.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

TOPIC_SEEDS = {
    "cost_of_living": ["inflation", "prices", "cost of living", "rent", "wages", "tariff"],
    "health_care": ["health care", "healthcare", "insurance", "drug prices", "medicaid", "medicare"],
    "immigration": ["immigration", "border", "deportation", "asylum", "ICE"],
    "democracy_rights": ["abortion", "reproductive", "voting rights", "democracy", "election integrity"],
    "foreign_policy_energy": ["Iran", "Ukraine", "Israel", "war", "gas prices", "energy"],
}
MIDTERM_EVENT_SLUG = "balance-of-power-2026-midterms"

EQUITY_BASKET = pd.DataFrame(
    [
        ("XLP", "Consumer Staples Select Sector SPDR", "cost_of_living", "defensive consumption / real-income stress"),
        ("WMT", "Walmart", "cost_of_living", "value-trade-down exposure"),
        ("UNH", "UnitedHealth", "health_care", "health-policy / reimbursement sensitivity"),
        ("CVS", "CVS Health", "health_care", "drug-price and coverage policy sensitivity"),
        ("GEO", "GEO Group", "immigration", "immigration-detention policy sensitivity"),
        ("CXW", "CoreCivic", "immigration", "immigration-detention policy sensitivity"),
        ("NEE", "NextEra Energy", "foreign_policy_energy", "energy / climate-policy sensitivity"),
        ("XLE", "Energy Select Sector SPDR", "foreign_policy_energy", "energy-price and permitting sensitivity"),
    ], columns=["ticker", "name", "topic", "hypothesis"]
)

HEADERS = {"User-Agent": "FRE-GY-7871A academic research / contact: instructor"}


def load_project_secrets() -> None:
    """Load local, untracked credentials without overriding real environment variables.

    Put provider variables in ``secrets/social_api.env`` (or the legacy,
    provider-specific files). These files are excluded from Git. ``.env``
    remains supported for existing workflows.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[1]
    for filename in (".env", "secrets/social_api.env", "secrets/twitterapi_io.env", "secrets/reddit.env"):
        load_dotenv(root / filename, override=False)


def credential_status() -> dict[str, bool]:
    """Report provider readiness without exposing any secret values."""
    load_project_secrets()
    return {
        "twitterapi.io": bool(os.getenv("TWITTERAPI_IO_KEY")),
    }


def _get(url: str, params: dict | None = None, timeout: int = 30,
         headers: dict | None = None, attempts: int = 3):
    """GET JSON with bounded 429 backoff; never retries non-rate-limit errors."""
    merged_headers = {**HEADERS, **(headers or {})}
    for attempt in range(attempts):
        response = requests.get(url, params=params, headers=merged_headers, timeout=timeout)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        if attempt == attempts - 1:
            response.raise_for_status()
        retry_after = response.headers.get("Retry-After")
        # GDELT asks clients to leave at least five seconds between requests.
        # Use a six-second floor when no provider-specific Retry-After is sent.
        wait_seconds = min(float(retry_after), 60) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(max(6, 2 ** (attempt + 1)), 30)
        print(f"HTTP 429 from {url}; retrying in {wait_seconds:.0f}s ({attempt + 1}/{attempts - 1})")
        time.sleep(wait_seconds)
    raise RuntimeError("unreachable")


def fetch_gdelt(query: str, start: str, end: str, max_records: int = 250) -> pd.DataFrame:
    """Fetch English news article metadata from the public GDELT DOC 2.0 API."""
    data = _get("https://api.gdeltproject.org/api/v2/doc/doc", {
        "query": query, "mode": "artlist", "format": "json", "maxrecords": max_records,
        "startdatetime": pd.Timestamp(start).strftime("%Y%m%d%H%M%S"),
        "enddatetime": pd.Timestamp(end).strftime("%Y%m%d%H%M%S"),
        "format": "json", "sourcelang": "english",
    })
    rows = data.get("articles", [])
    return pd.DataFrame([{
        "date": a.get("seendate", "")[:8], "text": f"{a.get('title', '')}. {a.get('url', '')}",
        "source": "gdelt", "url": a.get("url"), "title": a.get("title"),
    } for a in rows])


def fetch_google_news_rss(query: str, start: str, end: str) -> pd.DataFrame:
    """Fetch public Google News RSS metadata; no API credential is required."""
    params = {"q": f"{query} after:{start} before:{end}", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    response = requests.get("https://news.google.com/rss/search", params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = []
    for item in root.findall("./channel/item"):
        rows.append({
            "date": item.findtext("pubDate"), "text": item.findtext("title", ""), "source": "google_news_rss",
            "url": item.findtext("link"), "title": item.findtext("title"),
        })
    return pd.DataFrame(rows, columns=["date", "text", "source", "url", "title"])


def fetch_hackernews(query: str, limit: int = 100) -> pd.DataFrame:
    """Search public Hacker News stories/comments through the Algolia API."""
    payload = _get("https://hn.algolia.com/api/v1/search_by_date", {
        "query": query, "tags": "(story,comment)", "hitsPerPage": limit,
    })
    rows = []
    for hit in payload.get("hits", []):
        text = hit.get("title") or hit.get("comment_text") or ""
        object_id = hit.get("objectID")
        rows.append({
            "date": hit.get("created_at"), "text": re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text))).strip(),
            "source": "hacker_news", "url": hit.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else None),
            "title": hit.get("title"),
        })
    return pd.DataFrame(rows, columns=["date", "text", "source", "url", "title"])


def fetch_mastodon(tags: Iterable[str] = ("midterms", "election2026", "uspolitics"), limit: int = 40) -> pd.DataFrame:
    """Collect public posts from Mastodon's tag timelines; no credential required."""
    rows = []
    for tag in tags:
        payload = _get(f"https://mastodon.social/api/v1/timelines/tag/{tag}", {"limit": limit})
        for post in payload:
            if post.get("language") not in (None, "en"):
                continue
            text = unescape(re.sub(r"<[^>]+>", " ", post.get("content", "")))
            rows.append({
                "date": post.get("created_at"), "text": re.sub(r"\s+", " ", text).strip(), "source": "mastodon",
                "url": post.get("url"), "title": None,
            })
    return pd.DataFrame(rows, columns=["date", "text", "source", "url", "title"])


def fetch_twitterapi(query: str, start: str, end: str, max_pages: int | None = None) -> pd.DataFrame:
    """Collect X posts through twitterapi.io's read-only advanced-search endpoint.

    Requires ``TWITTERAPI_IO_KEY``. The page cap is intentionally small because
    twitterapi.io bills by returned post; override it only after deciding a budget.
    """
    load_project_secrets()
    key = os.getenv("TWITTERAPI_IO_KEY")
    if not key:
        raise RuntimeError("TWITTERAPI_IO_KEY is required. Add it to secrets/social_api.env before collecting text.")
    max_pages = max_pages or int(os.getenv("TWITTERAPI_MAX_PAGES", "3"))
    full_query = f"({query}) since:{start} until:{end} lang:en -filter:retweets"
    rows, cursor = [], None
    for _ in range(max_pages):
        params = {"query": full_query, "queryType": "Latest"}
        if cursor:
            params["cursor"] = cursor
        payload = _get("https://api.twitterapi.io/twitter/tweet/advanced_search", params=params,
                       headers={"X-API-Key": key})
        tweets = payload.get("tweets", [])
        for tweet in tweets:
            created = tweet.get("createdAt", tweet.get("created_at"))
            rows.append({
                "date": created, "text": tweet.get("text", ""), "source": "twitterapi.io",
                "url": tweet.get("url") or (f"https://x.com/i/status/{tweet['id']}" if tweet.get("id") else None),
                "title": None,
            })
        cursor = payload.get("next_cursor")
        if not cursor or not tweets:
            break
    return pd.DataFrame(rows, columns=["date", "text", "source", "url", "title"])


def collect_text(start: str, end: str) -> pd.DataFrame:
    """Collect cross-source election discussion; deduplicate and retain provenance."""
    load_project_secrets()
    query = '(midterm OR congress OR election) AND (inflation OR healthcare OR immigration OR abortion OR economy)'
    # X advanced-search syntax treats adjacent groups as an AND; do not send the
    # literal word "AND" as a search term.
    twitter_query = '(midterm OR congress OR election) (inflation OR healthcare OR immigration OR abortion OR economy)'
    frames = []
    providers = (
        ("gdelt", lambda: fetch_gdelt(query, start, end)),
        ("google_news_rss", lambda: fetch_google_news_rss(query, start, end)),
        ("hacker_news", lambda: fetch_hackernews("midterms", 100)),
        ("mastodon", lambda: fetch_mastodon()),
        ("twitterapi.io", lambda: fetch_twitterapi(twitter_query, start, end)),
    )
    for provider, fn in providers:
        try:
            frame = fn()
            print(f"{provider}: {len(frame):,} rows returned")
            if not frame.empty:
                frames.append(frame)
        except requests.HTTPError as exc:
            response = exc.response
            detail = (response.text or "").replace("\n", " ")[:240] if response is not None else str(exc)
            status = response.status_code if response is not None else "unknown"
            print(f"{provider}: skipped (HTTP {status}; {detail})")
        except requests.RequestException as exc:
            print(f"{provider}: skipped ({exc})")
    if not frames:
        return pd.DataFrame(columns=["date", "text", "source", "url", "title"])
    out = pd.concat(frames, ignore_index=True).dropna(subset=["text"])
    # Providers mix compact GDELT dates (YYYYMMDD), RFC-822 RSS dates, and ISO-8601
    # timestamps. ``format='mixed'`` prevents Pandas from inferring GDELT's format
    # once and coercing every other provider's timestamps to NaT.
    out["date"] = pd.to_datetime(out["date"], errors="coerce", format="mixed", utc=True).dt.tz_localize(None).dt.normalize()
    start_date, end_date = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    out = (out.dropna(subset=["date"]).loc[lambda x: x["date"].between(start_date, end_date)]
           .drop_duplicates(subset=["text"]).reset_index(drop=True))
    print("Retained after date filtering/deduplication:", out.groupby("source").size().to_dict())
    return out


def discover_polymarket_sweep() -> pd.DataFrame:
    """Find Democratic-sweep contracts, including Polymarket's balance-of-power event."""
    # The direct event endpoint catches Polymarket's compact outcome label
    # ("D Senate, D House"), which does not contain the word "Democrat".
    event = _get(f"https://gamma-api.polymarket.com/events/slug/{MIDTERM_EVENT_SLUG}")
    if isinstance(event, dict):
        markets = event.get("markets", [])
    else:
        markets = []
    if not markets:
        markets = _get("https://gamma-api.polymarket.com/markets", {"active": "true", "closed": "false", "limit": 500})
        if isinstance(markets, dict):
            markets = markets.get("data", markets.get("markets", []))
    canonical_columns = ["id", "question", "slug", "clobTokenIds", "outcomes", "outcomePrices", "liquidityNum", "volumeNum"]
    if not isinstance(markets, list) or not markets:
        return pd.DataFrame(columns=canonical_columns)
    frame = pd.DataFrame(markets)
    question = frame.get("question", pd.Series(dtype=str)).fillna("")
    slug = frame.get("slug", pd.Series(dtype=str)).fillna("")
    mask = (question.str.contains(r"(?:democrat.*sweep|democrat.*(?:house|senate)|house.*democrat|senate.*democrat|congress.*democrat)", case=False, regex=True)
            | slug.str.contains(r"(?:d-senate-d-house|democrats?-sweep)", case=False, regex=True))
    cols = [c for c in canonical_columns if c in frame]
    result = frame.loc[mask, cols].copy()
    for col in canonical_columns:
        if col not in result:
            result[col] = np.nan
    return result[canonical_columns].sort_values("liquidityNum", ascending=False, na_position="last").reset_index(drop=True)


def polymarket_history(clob_token_id: str, start_ts: int, end_ts: int, fidelity: int = 1440,
                       interval: str = "max") -> pd.DataFrame:
    """Retrieve daily midpoint history for the YES token from Polymarket CLOB.

    Polymarket rejects long explicit start/end spans. ``interval=max`` requests
    its supported full history, which is then restricted locally to the study span.
    """
    params = {"market": clob_token_id, "interval": interval, "fidelity": fidelity}
    if interval != "max":
        params.update({"startTs": start_ts, "endTs": end_ts})
    data = _get("https://clob.polymarket.com/prices-history", params)
    rows = data.get("history", data) if isinstance(data, dict) else data
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["date", "sweep_probability"])
    time_col, price_col = ("t", "p") if {"t", "p"}.issubset(out.columns) else (out.columns[0], out.columns[1])
    out["date"] = pd.to_datetime(out[time_col], unit="s", utc=True).dt.tz_convert(None).dt.normalize()
    out = out.rename(columns={price_col: "sweep_probability"})[["date", "sweep_probability"]].drop_duplicates("date")
    start_date = pd.to_datetime(start_ts, unit="s").normalize()
    end_date = pd.to_datetime(end_ts, unit="s").normalize()
    return out.loc[out["date"].between(start_date, end_date)].reset_index(drop=True)


def choose_yes_token(market_row: pd.Series) -> str:
    """Parse Gamma JSON fields and return the token corresponding to the literal YES outcome."""
    outcomes = json.loads(market_row["outcomes"]) if isinstance(market_row["outcomes"], str) else market_row["outcomes"]
    tokens = json.loads(market_row["clobTokenIds"]) if isinstance(market_row["clobTokenIds"], str) else market_row["clobTokenIds"]
    idx = [str(x).strip().lower() for x in outcomes].index("yes")
    return tokens[idx]


def seed_topic_labels(text: pd.Series) -> pd.Series:
    """Transparent fallback label, used to aggregate if BERTopic is unavailable."""
    lowered = text.fillna("").str.lower()
    scores = pd.DataFrame({name: lowered.str.count("|".join(map(str.lower, words))) for name, words in TOPIC_SEEDS.items()})
    return scores.idxmax(axis=1).where(scores.max(axis=1).gt(0), "other")


def sentiment_score(text: pd.Series) -> pd.Series:
    """VADER compound score; replace with FinBERT in notebook when transformer stack is present."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    return text.fillna("").map(lambda x: analyzer.polarity_scores(x)["compound"])


def topic_daily_index(documents: pd.DataFrame, label_col: str = "topic") -> pd.DataFrame:
    data = documents.copy()
    data["sentiment"] = sentiment_score(data["text"])
    daily = (data.groupby(["date", label_col]).agg(sentiment=("sentiment", "mean"), mentions=("text", "size"))
             .reset_index())
    daily["salience"] = daily.groupby("date")["mentions"].transform(lambda x: x / x.sum())
    # A volume-aware signed attention measure, but preserve its components for auditability.
    daily["sentiment_index"] = daily["sentiment"] * np.log1p(daily["mentions"])
    return daily


def market_adjusted_returns(tickers: Iterable[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    symbols = list(dict.fromkeys([*tickers, "SPY"]))
    close = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    returns = close.pct_change().dropna(how="all")
    market = returns["SPY"]
    excess = returns.drop(columns="SPY").sub(market, axis=0)
    return excess.rename_axis("date").reset_index().melt("date", var_name="ticker", value_name="market_adjusted_return")


def correlation_table(topic_index: pd.DataFrame, sweep: pd.DataFrame, min_obs: int = 20) -> pd.DataFrame:
    merged = topic_index.merge(sweep, on="date", how="inner")
    rows = []
    for topic, g in merged.groupby("topic"):
        g = g.dropna(subset=["sentiment_index", "sweep_probability"])
        if len(g) >= min_obs:
            rows.append({"topic": topic, "n": len(g), "pearson_r": g["sentiment_index"].corr(g["sweep_probability"]),
                         "spearman_r": g["sentiment_index"].corr(g["sweep_probability"], method="spearman")})
    return pd.DataFrame(rows)
