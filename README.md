# 2026 U.S. Midterm Voter-Issues, Sentiment, and Market Basket

This project is a reproducible research pipeline for three linked questions:

1. Which election issues are most salient in U.S. news and public social discussion?
2. Does topic-specific sentiment co-move with the prediction-market probability of a Democratic congressional sweep?
3. Does an issue-sensitive equity basket earn abnormal returns as that sentiment changes?

Start with [`midterm_sentiment_analysis.ipynb`](midterm_sentiment_analysis.ipynb). It discovers public Polymarket/Kalshi election contracts, collects text, discovers topics, scores topic sentiment, calculates correlations and rolling regressions, and evaluates the equity basket against SPY. The notebook deliberately refuses to manufacture correlations when an API has not supplied enough overlapping observations.

## Quick start

For the full BERTopic/transformer path, use Python 3.12. The Python 3.13
environment on this machine does not have a compatible PyTorch wheel.

```bash
conda env create -f environment.yml
conda activate fre-gy-7871a-a5
python -m ipykernel install --user --name fre-gy-7871a-a5 --display-name "Python (FRE-GY Assignment 5)"
jupyter lab
```

The seed-label topic fallback works without BERTopic. If it prints
`BERTopic unavailable (ModuleNotFoundError)`, that is an informational message,
not a failed notebook run.

For the lightweight fallback-only path:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export NEWSAPI_KEY="..."             # optional but recommended
export TWITTERAPI_IO_KEY="..."       # required; twitterapi.io X-post search
export TWITTERAPI_MAX_PAGES=3         # explicit cost/coverage cap
jupyter lab
```

The default public collection path is GDELT, Google News RSS, **Hacker News public search**, Mastodon public tag timelines, and required X posts through twitterapi.io, plus Polymarket's public Gamma/CLOB endpoints. The X collector uses only read-only advanced search, caps retrieval at three pages by default, and preserves source/URL provenance. Review the provider's current terms and billing before raising the cap.

Instead of exporting the X key in every terminal, create [`secrets/twitterapi_io.env`](secrets/README.md) (the actual key file is Git-ignored). The collector loads it automatically and will retry a rate-limited request up to twice with `Retry-After` or exponential backoff. Keep `TWITTERAPI_MAX_PAGES` low; reducing pages, narrowing dates, and waiting for the indicated reset are the right remedies for repeated HTTP 429 responses.

If Polymarket discovery returns no suitable active contract, do not invent one. Inspect the exact current market and set `POLYMARKET_YES_TOKEN` to its literal YES CLOB token in a local secrets file; the notebook will then retrieve that token's history. A direct Democratic-sweep contract is preferred. Otherwise, construct and document a House/Senate probability product separately.

See [`REPORT.md`](REPORT.md) for methods, scope, preliminary evidence, equity mappings, and interpretation; [`AI_USE.md`](AI_USE.md) records how AI was used. Do not treat this project as investment advice or an election forecast.
