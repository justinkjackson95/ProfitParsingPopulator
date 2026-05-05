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

async def fetch_daily_bars(ticker: str, client: httpx.AsyncClient) -> Optional[pd.DataFrame]:
    """Fetch 60 days of daily OHLCV from Alpha Vantage (free tier)."""
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
        df = pd.DataFrame(rows).set_index("date").sort_index()
        return df.tail(60)
    except Exception:
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


def compute_features(ticker: str, df: pd.DataFrame) -> dict:
    closes = df["close"]
    return {
        "ticker":       ticker,
        "price":        round(float(closes.iloc[-1]), 2),
        "rsi":          compute_rsi(closes),
        "macd":         compute_macd(closes),
        "ema21_dist":   compute_ema_distance(closes, 21),
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
- EMA-21 distance: +1% to +8% above = healthy trend; > +10% = extended
- ATR % (volatility): higher ATR = larger potential swing, but also more risk
- RVOL > 1.5: institutional/unusual interest — strong signal
- 1-day and 5-day % change: captures short-term price momentum

Return ONLY a valid JSON array (no markdown, no explanation) in this exact format:
[
  {"ticker": "XXXX", "prob": 0.72, "rationale": "one sentence"},
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
    for ticker, df in zip(ticker_list, results):
        if df is not None and len(df) >= 30:
            try:
                features_list.append(compute_features(ticker, df))
            except Exception:
                pass  # Skip tickers with insufficient data

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
