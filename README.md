# AI Trading Bot Pro Max Ultra Plus 9000

Local pipeline: Yahoo Finance BTC news → FinBERT sentiment → CoinGecko technicals → combined signal → SQLite + paper trades → **Next.js + FastAPI dashboard** + daily markdown reports.

## Setup

Use a **virtual environment** (system Python on macOS often blocks `pip install -e .` without sudo).

```bash
cd btc-ai-paper-trading
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .
cp .env.example .env   # optional
```

Run commands from this directory so relative paths like `data/bot.db` resolve correctly.

First sentiment run downloads FinBERT weights (Transformers + PyTorch; large download).

## Test scraper + sentiment only (no DB / no CoinGecko)

```bash
btc-paper-test-news
```

## Run once (full pipeline)

```bash
btc-paper-run
```

## ML layer (optional)

1. Build a training CSV from SQLite (1h candles + signals):

   ```bash
   btc-paper-export-ml-features --output data/ml_features.csv
   ```

2. Train per-horizon models (writes `models/*.joblib` + `models/model_metadata.json`):

   ```bash
   btc-paper-train-ml --csv data/ml_features.csv --output-dir models
   ```

3. Enable inference (default `ML_ENABLED=true` in code). With artifacts present, the next `btc-paper-run` blends **news + technical + ML** (defaults **0.3 / 0.3 / 0.4**). If models are missing, the bot falls back to the classic **0.6 / 0.4** news vs technical mix.

4. **Notebook (modeling walkthrough):** `notebooks/ml_portfolio_showcase.ipynb` — nine-part showcase (intro → load → clean → EDA → features → train → predict → app blend → conclusion), heavy markdown + Plotly, same `btc_paper.ml` / `signal_engine` code as production. All imports are in the **first** code cell; the next code cell sets paths — **Run All** top to bottom.

   From the repo root: `pip install ipykernel jupyter` then `jupyter notebook notebooks/ml_portfolio_showcase.ipynb`.

## Dashboard (React + API)

1. One-time: install the Python package with the API extra (from repo root):

   ```bash
   pip install -e '.[api]'
   ```

2. Install web dependencies and start **Next.js + `btc-paper-api` together** (Ctrl+C stops both).

   **From the repo root** (recommended — one command):

   ```bash
   npm install          # also runs npm install in web/ via postinstall
   npm run dev
   ```

   Or from **`web/`** only:

   ```bash
   cd web
   cp .env.example .env.local   # optional; for local dev leave NEXT_PUBLIC_API_URL unset (Next proxies /api → FastAPI)
   npm install
   npm run dev
   ```

   In **Cursor / VS Code**: Command Palette → **Tasks: Run Task** → **Dev: API + Next.js**.

   The API runs from the **repo root** so `data/bot.db` and `.env` resolve. Default API: `http://127.0.0.1:8000`. Frontend-only: `npm run dev:web` (from `web/`) or `npm run dev:web` (from root).

3. Optional: start the backend manually in another terminal:

   ```bash
   btc-paper-api
   ```

   Open the printed localhost URL (often port 3000) for the app (Overview, News, Technical, Paper trading, Trades, Market analysis, ML). `/welcome` redirects to Overview.

## Daily scheduler (9:00 Asia/Singapore)

```bash
btc-paper-scheduler
```

## CoinGecko 429 (rate limit)

The free API allows only a few calls per minute; rapid repeated fetches can hit **429 Too Many Requests**.

Mitigations in code:

- **In-process response cache** (default **120s**, `COINGECKO_CACHE_TTL`) shared by all endpoints (`simple/price`, `market_chart`, `ohlc`).
- **More retries** with exponential backoff and **`Retry-After`** when CoinGecko sends it (`COINGECKO_MAX_RETRIES`, default 5).

To go further: use a **CoinGecko Pro** key / demo plan, increase cache TTL, or rely on **last signal price** from SQLite when live fetch fails.

## Disclaimer

Paper trading only; not financial advice. News and prices can be wrong or delayed.
