# 🚀 AI Stock Momentum Screener

An AI-powered stock screener that ranks tickers by probability of a **+10% move in 1–5 days** using technical features fed to Claude for ranking.

```
NVDA  ████████████████░░░░  78%  RSI:64 RVOL:2.3× MACD:▲
TSLA  █████████████░░░░░░░  65%  RSI:58 RVOL:1.8× MACD:▲
PLTR  ██████████░░░░░░░░░░  52%  RSI:61 RVOL:3.1× MACD:▲
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend (Vercel)                                │
│  - Table of tickers + probability scores                │
│  - Auto-refresh every 45s                               │
└───────────────────┬─────────────────────────────────────┘
                    │ GET /api/screen
┌───────────────────▼─────────────────────────────────────┐
│  FastAPI Backend (Railway / Render)                     │
│  1. Fetch OHLCV bars (Alpha Vantage)                    │
│  2. Compute RSI, MACD, EMA, ATR, RVOL                  │
│  3. Send features → Claude for probability ranking      │
│  4. Return JSON                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Anthropic API key (https://console.anthropic.com)
- Alpha Vantage API key — free at https://alphavantage.co (500 req/day)

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export ALPHA_VANTAGE_KEY=YOUR_KEY   # or leave as "demo" for very limited testing

uvicorn main:app --reload --port 8000
```

Test it:
```bash
curl http://localhost:8000/api/screen
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

The Vite dev server proxies `/api` → `localhost:8000` automatically.

---

## API Reference

### `GET /api/screen`

**Query params:**
| Param | Default | Description |
|-------|---------|-------------|
| `tickers` | 15 default tickers | Comma-separated list, e.g. `?tickers=AAPL,TSLA,NVDA` |

**Response:**
```json
{
  "tickers": [
    {
      "ticker": "NVDA",
      "price": 875.40,
      "prob": 0.78,
      "rationale": "Strong RVOL surge with bullish MACD crossover and RSI in momentum zone.",
      "rsi": 64.2,
      "macd": { "macd": 8.21, "signal": 5.13, "hist": 3.08 },
      "ema21_dist": 3.4,
      "atr_pct": 2.8,
      "rvol": 2.3,
      "chg_1d_pct": 2.1,
      "chg_5d_pct": 8.4
    }
  ],
  "computed_at": "2024-10-15T14:32:00Z",
  "duration_ms": 4820
}
```

---

## The Claude Prompt

```
You are a quantitative momentum trader.
Your task is to rank stocks by their probability of achieving a +10% price 
move within the next 1-5 trading days.

Scoring framework:
- RSI 50–70: bullish momentum (RSI > 80 = overextended; RSI < 40 = bearish)
- MACD histogram turning positive / accelerating: bullish signal
- EMA-21 distance: +1% to +8% above = healthy trend; > +10% = extended
- ATR % (volatility): higher ATR = larger potential swing
- RVOL > 1.5: unusual interest — strong signal
- 1D/5D % change: captures short-term price momentum

Return ONLY a JSON array sorted descending by prob (0.01–0.99).
```

---

## Deployment

### Backend → Railway

1. Push `backend/` to a GitHub repo
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Set environment variables:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ALPHA_VANTAGE_KEY=YOUR_KEY
   PORT=8000
   ```
4. Railway auto-detects `Procfile` and deploys
5. Copy the generated URL (e.g. `https://momentum-screener.up.railway.app`)

**Alternative: Render**
- Connect repo at https://render.com → New Web Service
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Add env vars as above

### Frontend → Vercel

1. Push `frontend/` to a GitHub repo (or same repo, different folder)
2. Go to https://vercel.com → New Project → Import
3. Set environment variable:
   ```
   VITE_API_URL=https://YOUR_RAILWAY_URL
   ```
4. Deploy → done in ~60 seconds

---

## Customizing the Ticker List

Edit `DEFAULT_TICKERS` in `backend/main.py`, or pass tickers as a query param:

```
/api/screen?tickers=SPY,QQQ,IWM,GLD,ARKK
```

---

## Rate Limits & Cost

| Service | Free tier | Cost at scale |
|---------|-----------|---------------|
| Alpha Vantage | 25 req/min, 500/day | $50/mo for 75 req/min |
| Anthropic Claude | Pay per token | ~$0.002 per screen call |
| Vercel | Unlimited hobby | Free |
| Railway | $5 credit/mo | ~$5–10/mo for always-on |

**Tip:** Cache the Alpha Vantage results in memory for 60s to avoid hitting rate limits on rapid refreshes.

---

## Upgrade Path

Once the MVP is validated:

1. **Better data**: Replace Alpha Vantage with Polygon.io or Alpaca (real-time)
2. **More features**: Add options flow, news sentiment, insider buying
3. **Cache layer**: Redis for API response caching
4. **Auth**: Clerk.dev for user accounts in < 1 hour
5. **Database**: Supabase for storing scan history
6. **Alerts**: Resend for email alerts on high-conviction signals

---

> ⚠️ **Disclaimer**: This tool is for educational and research purposes only. It is not financial advice. Past technical patterns do not guarantee future price movements. Always do your own research.
