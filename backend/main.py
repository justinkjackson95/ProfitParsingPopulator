"""
AI Stock Momentum Screener — FastAPI Backend
Ranks tickers by probability of a +10% move in 1-5 days using
technical features + Claude AI scoring.
"""

import os
import json
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = FastAPI(title="AI Momentum Screener", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "demo")  # free tier works for MVP

# Default watchlist — swap for any tickers you care about
DEFAULT_TICKERS = [
    "NVDA", "TSLA", "AAPL", "MSFT", "META",
    "AMZN", "GOOGL", "AMD", "PLTR", "SMCI",
    "MSTR", "COIN", "UBER", "CRWD", "SNOW",
]

# ── Data fetching ─────────────────────────────────────────────────────────────

# In-memory cache: {ticker: (fetched_at, dataframe)}
# Daily bars don't change intraday — once we have today's data it's good until
# the next market close. 12h TTL keeps us under Alpha Vantage's 25/day free tier
# regardless of how often the screener auto-refreshes.
# TODO when going live: replace with yfinance / Finnhub for fresh intraday data.
_BARS_CACHE: dict[str, tuple[datetime, pd.DataFrame]] = {}
_CACHE_TTL = timedelta(hours=12)


async def fetch_daily_bars(ticker: str, client: httpx.AsyncClient) -> Optional[pd.DataFrame]:
    """Fetch 90 days of daily OHLCV. Cached in memory for 12h to spare API quota.
    On rate-limit or API failure, falls back to stale cache if any exists."""
    now = datetime.utcnow()

    # 1. Fresh cache hit
    cached = _BARS_CACHE.get(ticker)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    # 2. Cache miss or expired — try the API
    url = (
        "https://www.alphavantage.co/query"
        f"?function=TIME_SERIES_DAILY&symbol={ticker}"
        f"&outputsize=compact&apikey={ALPHA_VANTAGE_KEY}"
    )
    try:
        r = await client.get(url, timeout=10)
        data = r.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            # 3. API returned nothing (rate limit / quota / bad ticker).
            #    Serve stale cache as a fallback so demos don't go blank.
            if cached:
                print(f"[cache] {ticker}: API empty, serving stale cache from {cached[0].isoformat()}Z")
                return cached[1]
            return None
        rows = []
        for date_str, bar in sorted(ts.items()):
            rows.append({
                "date": date_str,
                "open":  float(bar["1. open"]),
                "high":  float(bar["2. high"]),
                "low":   float(bar["3. low"]),
                "close": float(bar["4. close"]),
                "volume": float(bar["5. volume"]),
            })
        df = pd.DataFrame(rows).set_index("date").sort_index().tail(90)
        _BARS_CACHE[ticker] = (now, df)
        print(f"[cache] {ticker}: fetched fresh, cached ({len(df)} bars)")
        return df
    except Exception as e:
        # On any exception, serve stale if we have it
        if cached:
            print(f"[cache] {ticker}: fetch error {e!r}, serving stale cache")
            return cached[1]
        return None


# ── Technical indicators ──────────────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def compute_macd(series: pd.Series) -> dict:
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return {
        "macd":   round(float(macd_line.iloc[-1]), 4),
        "signal": round(float(signal.iloc[-1]), 4),
        "hist":   round(float(hist.iloc[-1]), 4),
    }


def compute_ema_distance(series: pd.Series, span: int = 21) -> float:
    """% distance of last close above/below EMA."""
    ema = series.ewm(span=span, adjust=False).mean()
    dist = (series.iloc[-1] - ema.iloc[-1]) / ema.iloc[-1] * 100
    return round(float(dist), 2)


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=period - 1, min_periods=period).mean()
    # Express as % of close
    atr_pct = atr.iloc[-1] / close.iloc[-1] * 100
    return round(float(atr_pct), 2)


def compute_rvol(df: pd.DataFrame, period: int = 20) -> float:
    """Relative volume: today's volume vs 20-day average."""
    avg_vol = df["volume"].iloc[-period-1:-1].mean()
    if avg_vol == 0:
        return 1.0
    rvol = df["volume"].iloc[-1] / avg_vol
    return round(float(rvol), 2)


def compute_ema_stack(df: pd.DataFrame) -> dict:
    """EMA 9/13/50 stack analysis: trend ordering + compression flag."""
    closes = df["close"]
    price = float(closes.iloc[-1])
    ema9  = float(closes.ewm(span=9,  adjust=False).mean().iloc[-1])
    ema13 = float(closes.ewm(span=13, adjust=False).mean().iloc[-1])
    ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

    if price > ema9 > ema13 > ema50:
        stack = "bullish"
    elif price < ema9 < ema13 < ema50:
        stack = "bearish"
    else:
        stack = "mixed"

    # Compression: EMA9 and EMA13 hugging each other often precedes a breakout
    spread_9_13_pct = abs(ema9 - ema13) / ema13 * 100
    compressed = spread_9_13_pct < 0.5

    return {
        "stack":           stack,
        "compressed":      compressed,
        "ema9":            round(ema9, 2),
        "ema13":           round(ema13, 2),
        "ema50":           round(ema50, 2),
        "dist_ema9_pct":   round((price - ema9)  / ema9  * 100, 2),
        "dist_ema50_pct": round((price - ema50) / ema50 * 100, 2),
    }


def compute_fib_levels(df: pd.DataFrame, window: int = 30) -> dict:
    """50% and 61.8% Fibonacci retracements over the recent swing window."""
    recent = df.tail(window)
    swing_high = float(recent["high"].max())
    swing_low  = float(recent["low"].min())
    rng = swing_high - swing_low
    price = float(df["close"].iloc[-1])

    if rng == 0:
        return {
            "swing_high": swing_high, "swing_low": swing_low,
            "fib_50": swing_high, "fib_618": swing_high,
            "price_vs_fib_50_pct": 0.0, "price_vs_fib_618_pct": 0.0,
            "near_key_fib": False,
        }

    fib_50  = swing_low + rng * 0.5
    fib_618 = swing_low + rng * 0.618
    dist_50_pct  = (price - fib_50)  / fib_50  * 100
    dist_618_pct = (price - fib_618) / fib_618 * 100

    return {
        "swing_high":            round(swing_high, 2),
        "swing_low":             round(swing_low, 2),
        "fib_50":                round(fib_50, 2),
        "fib_618":               round(fib_618, 2),
        "price_vs_fib_50_pct":   round(dist_50_pct, 2),
        "price_vs_fib_618_pct":  round(dist_618_pct, 2),
        "near_key_fib":          abs(dist_50_pct) < 1.0 or abs(dist_618_pct) < 1.0,
    }


def compute_features(ticker: str, df: pd.DataFrame) -> dict:
    closes = df["close"]
    return {
        "ticker":       ticker,
        "price":        round(float(closes.iloc[-1]), 2),
        "rsi":          compute_rsi(closes),
        "macd":         compute_macd(closes),
        "ema21_dist":   compute_ema_distance(closes, 21),
        "ema_stack":    compute_ema_stack(df),
        "fib":          compute_fib_levels(df),
        "atr_pct":      compute_atr(df),
        "rvol":         compute_rvol(df),
        "chg_1d_pct":   round(float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100), 2),
        "chg_5d_pct":   round(float((closes.iloc[-1] / closes.iloc[-6] - 1) * 100), 2),
    }


# ── Claude ranking ────────────────────────────────────────────────────────────

CLAUDE_PROMPT = """You are a quantitative momentum trader. 
Your task is to rank the following stocks by their probability of achieving a +10% price move within the next 1-5 trading days.

Use ONLY the technical features provided. Do NOT rely on fundamental knowledge or news.

Scoring framework:
- RSI 50–70: bullish momentum (RSI > 80 = overextended risk; RSI < 40 = bearish)
- MACD histogram turning positive / accelerating: bullish signal
- EMA stack "bullish" (price > EMA9 > EMA13 > EMA50): strongest trend confirmation; "bearish" = fade; "mixed" = no clean trend
- EMA compression (ema9_13 within 0.5%): coiling pattern — combined with RVOL > 1.5 this is a high-probability breakout setup
- EMA-21 distance: +1% to +8% above = healthy trend; > +10% = extended
- Fib retracement: when price is within 1% of the 50% or 61.8% level (near_key_fib=true) of the 30-day swing, it's a high-probability bounce/continuation zone — strongest when ema_stack is bullish (pullback in an uptrend)
- ATR % (volatility): higher ATR = larger potential swing, but also more risk
- RVOL > 1.5: institutional/unusual interest — strong signal
- 1-day and 5-day % change: captures short-term price momentum

Synergy patterns to favor (rank these higher):
- ema_stack=bullish + near_key_fib=true + rvol > 1.5: textbook continuation entry
- ema_stack=bullish + compressed=true + rvol rising: imminent breakout
- ema_stack=mixed but RSI 55-65 + MACD hist accelerating: early trend reversal

Return ONLY a valid JSON array (no markdown, no explanation) in this exact format:
[
  {{"ticker": "XXXX", "prob": 0.72, "rationale": "one sentence"}},
  ...
]

prob must be between 0.01 and 0.99. Sort descending by prob.

Stock features:
{features_json}
"""

async def rank_with_claude(features_list: list[dict]) -> list[dict]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    prompt = CLAUDE_PROMPT.format(features_json=json.dumps(features_list, indent=2))

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

    if r.status_code != 200:
        raise HTTPException(502, f"Claude API error: {r.text}")

    raw = r.json()["content"][0]["text"].strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    rankings = json.loads(raw.strip())

    # Merge rankings back with full feature data
    feature_map = {f["ticker"]: f for f in features_list}
    result = []
    for item in rankings:
        t = item["ticker"]
        merged = {**feature_map.get(t, {}), **item}
        result.append(merged)

    return result


# ── Endpoint ──────────────────────────────────────────────────────────────────

class ScreenerResponse(BaseModel):
    tickers: list[dict]
    computed_at: str
    duration_ms: int


@app.get("/api/screen", response_model=ScreenerResponse)
async def screen(tickers: str = ",".join(DEFAULT_TICKERS)):
    t0 = datetime.utcnow()
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    # Fetch market data concurrently
    async with httpx.AsyncClient() as client:
        tasks = [fetch_daily_bars(t, client) for t in ticker_list]
        results = await asyncio.gather(*tasks)

    # Compute features for tickers with valid data
    features_list = []
    skipped = []
    for ticker, df in zip(ticker_list, results):
        if df is None:
            skipped.append(f"{ticker}: no data (rate limit or fetch error)")
            continue
        if len(df) < 60:
            skipped.append(f"{ticker}: only {len(df)} bars (need 60)")
            continue
        try:
            features_list.append(compute_features(ticker, df))
        except Exception as e:
            skipped.append(f"{ticker}: {type(e).__name__}: {e}")
    if skipped:
        print(f"[screen] skipped {len(skipped)}/{len(ticker_list)}: {'; '.join(skipped[:5])}")
    print(f"[screen] kept {len(features_list)} tickers")

    if not features_list:
        raise HTTPException(422, "No valid market data returned. Check your API key.")

    # Rank with Claude
    ranked = await rank_with_claude(features_list)

    duration = int((datetime.utcnow() - t0).total_seconds() * 1000)
    return ScreenerResponse(
        tickers=ranked,
        computed_at=datetime.utcnow().isoformat() + "Z",
        duration_ms=duration,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
