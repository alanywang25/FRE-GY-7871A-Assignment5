# Local API secrets

Created `social_api.env` in this directory with the provider credentials:

```dotenv
TWITTERAPI_IO_KEY=replace-with-your-twitterapi.io-key
```

Optional cost safeguard:

```dotenv
TWITTERAPI_MAX_PAGES=3
```

If automatic Polymarket discovery cannot find a current contract, add the
literal YES CLOB token only after checking the contract wording and resolution
rules:

```dotenv
POLYMARKET_YES_TOKEN=verified-yes-token
```

The pipeline loads this file automatically before it fetches X posts. Files in this directory are ignored by Git except for this guide; do not commit a key or paste it into the notebook. Environment variables still take precedence, so this is compatible with the Assignment 4 workflow or a shell-based setup. The legacy `twitterapi_io.env` remains supported.
