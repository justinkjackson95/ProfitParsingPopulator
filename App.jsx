import { useState, useEffect, useCallback, useRef } from "react";

// ── Config ────────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const REFRESH_INTERVAL = 45_000; // 45 seconds

// ── Helpers ───────────────────────────────────────────────────────────────────
function probColor(prob) {
  if (prob >= 0.7) return "#00ff88";
  if (prob >= 0.5) return "#ffe066";
  if (prob >= 0.35) return "#ff9f43";
  return "#ff5252";
}

function signColor(val) {
  return val >= 0 ? "#00ff88" : "#ff5252";
}

function fmt(val, decimals = 2, suffix = "") {
  if (val == null) return "—";
  const sign = val > 0 ? "+" : "";
  return `${sign}${Number(val).toFixed(decimals)}${suffix}`;
}

function ProbBar({ prob }) {
  return (
    <div style={{ position: "relative", height: 6, background: "#1a1a2e", borderRadius: 3, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          height: "100%",
          width: `${prob * 100}%`,
          background: probColor(prob),
          boxShadow: `0 0 8px ${probColor(prob)}88`,
          transition: "width 0.6s ease",
          borderRadius: 3,
        }}
      />
    </div>
  );
}

function Pill({ label, value, color }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 4,
      background: `${color}18`,
      border: `1px solid ${color}44`,
      color,
      fontSize: 11,
      fontFamily: "'JetBrains Mono', monospace",
      whiteSpace: "nowrap",
    }}>
      {label && <span style={{ opacity: 0.6, marginRight: 4 }}>{label}</span>}
      {value}
    </span>
  );
}

function CountdownBar({ total, elapsed }) {
  const pct = Math.min(elapsed / total, 1);
  return (
    <div style={{ height: 2, background: "#0d0d1a", position: "relative" }}>
      <div style={{
        position: "absolute",
        right: 0,
        top: 0,
        height: "100%",
        width: `${(1 - pct) * 100}%`,
        background: "linear-gradient(90deg, transparent, #4f8ef7)",
        transition: "width 1s linear",
      }} />
    </div>
  );
}

// ── Ticker row ─────────────────────────────────────────────────────────────────
function TickerRow({ item, rank, isNew }) {
  const [flash, setFlash] = useState(isNew);
  useEffect(() => {
    if (isNew) {
      const t = setTimeout(() => setFlash(false), 800);
      return () => clearTimeout(t);
    }
  }, [isNew]);

  const macdBull = item.macd?.hist > 0;

  return (
    <tr style={{
      background: flash ? "#00ff8810" : "transparent",
      transition: "background 0.8s ease",
      borderBottom: "1px solid #ffffff08",
    }}>
      {/* Rank */}
      <td style={{ padding: "12px 8px", textAlign: "center", color: "#ffffff30", fontSize: 12, fontFamily: "mono" }}>
        {String(rank).padStart(2, "0")}
      </td>

      {/* Ticker */}
      <td style={{ padding: "12px 16px" }}>
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: 1, color: "#f0f0ff" }}>
          {item.ticker}
        </div>
        <div style={{ fontSize: 11, color: "#ffffff40", marginTop: 2 }}>
          ${item.price?.toFixed(2)}
        </div>
      </td>

      {/* Probability */}
      <td style={{ padding: "12px 16px", minWidth: 120 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontSize: 18,
            fontWeight: 800,
            color: probColor(item.prob),
            fontFamily: "'JetBrains Mono', monospace",
            textShadow: `0 0 12px ${probColor(item.prob)}66`,
          }}>
            {(item.prob * 100).toFixed(0)}%
          </span>
        </div>
        <div style={{ marginTop: 4 }}>
          <ProbBar prob={item.prob} />
        </div>
      </td>

      {/* Signals */}
      <td style={{ padding: "12px 16px" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Pill label="RSI" value={item.rsi?.toFixed(0)} color={
            item.rsi > 70 ? "#ff9f43" : item.rsi > 50 ? "#00ff88" : "#ff5252"
          } />
          <Pill label="RVOL" value={item.rvol?.toFixed(2) + "×"} color={
            item.rvol > 2 ? "#00ff88" : item.rvol > 1.5 ? "#ffe066" : "#ffffff50"
          } />
          <Pill label="MACD" value={macdBull ? "▲" : "▼"} color={macdBull ? "#00ff88" : "#ff5252"} />
          <Pill label="ATR" value={item.atr_pct?.toFixed(1) + "%"} color="#4f8ef7" />
        </div>
      </td>

      {/* Price change */}
      <td style={{ padding: "12px 16px", textAlign: "right" }}>
        <div style={{ fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: signColor(item.chg_1d_pct) }}>
          {fmt(item.chg_1d_pct, 2, "%")} <span style={{ opacity: 0.5, fontSize: 11 }}>1D</span>
        </div>
        <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: signColor(item.chg_5d_pct), opacity: 0.7, marginTop: 2 }}>
          {fmt(item.chg_5d_pct, 2, "%")} <span style={{ opacity: 0.5 }}>5D</span>
        </div>
      </td>

      {/* EMA dist */}
      <td style={{ padding: "12px 16px", textAlign: "right" }}>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 12,
          color: signColor(item.ema21_dist),
        }}>
          {fmt(item.ema21_dist, 1, "%")}
          <div style={{ fontSize: 10, opacity: 0.4 }}>EMA21</div>
        </span>
      </td>

      {/* Rationale */}
      <td style={{ padding: "12px 24px 12px 8px", maxWidth: 260 }}>
        <div style={{
          fontSize: 11,
          color: "#ffffff50",
          lineHeight: 1.5,
          fontStyle: "italic",
        }}>
          {item.rationale || "—"}
        </div>
      </td>
    </tr>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [prevTickers, setPrevTickers] = useState([]);
  const lastFetchRef = useRef(Date.now());
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    lastFetchRef.current = Date.now();
    setElapsed(0);
    try {
      const r = await fetch(`${API_BASE}/api/screen`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json = await r.json();
      setPrevTickers(prev => {
        setData(json);
        return json.tickers?.map(t => t.ticker) || [];
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + interval
  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchData]);

  // Countdown ticker
  useEffect(() => {
    const t = setInterval(() => {
      setElapsed(Date.now() - lastFetchRef.current);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const isNew = (ticker) => !prevTickers.includes(ticker);
  const secLeft = Math.max(0, Math.round((REFRESH_INTERVAL - elapsed) / 1000));
  const tickers = data?.tickers || [];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#080810",
      color: "#e8e8f8",
      fontFamily: "'IBM Plex Sans', sans-serif",
    }}>
      {/* Google Fonts */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body { background: #080810; }

        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #0d0d1a; }
        ::-webkit-scrollbar-thumb { background: #2a2a4a; border-radius: 2px; }

        table { border-collapse: collapse; width: 100%; }

        tr:hover td { background: #ffffff04; }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }

        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .fade-in {
          animation: slideIn 0.4s ease forwards;
        }
      `}</style>

      {/* Header */}
      <div style={{
        background: "linear-gradient(180deg, #0d0d1f 0%, #080810 100%)",
        borderBottom: "1px solid #ffffff10",
        padding: "0 32px",
      }}>
        <div style={{ maxWidth: 1400, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 0 16px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#00ff88",
                  boxShadow: "0 0 8px #00ff88",
                  animation: "pulse 2s infinite",
                }} />
                <span style={{
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', monospace",
                  color: "#00ff8880",
                  letterSpacing: 3,
                  textTransform: "uppercase",
                }}>
                  LIVE
                </span>
              </div>
              <h1 style={{
                fontSize: 28,
                fontWeight: 700,
                letterSpacing: -0.5,
                marginTop: 6,
                background: "linear-gradient(135deg, #f0f0ff 0%, #8888cc 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}>
                Momentum Screener
              </h1>
              <p style={{ fontSize: 12, color: "#ffffff35", marginTop: 4, letterSpacing: 0.5 }}>
                AI-ranked probability of +10% move · 1–5 day window
              </p>
            </div>

            <div style={{ textAlign: "right" }}>
              <button
                onClick={fetchData}
                disabled={loading}
                style={{
                  background: loading ? "#1a1a2e" : "#1e1e3a",
                  border: "1px solid #4f8ef740",
                  color: loading ? "#4f8ef760" : "#4f8ef7",
                  padding: "8px 20px",
                  borderRadius: 6,
                  cursor: loading ? "wait" : "pointer",
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12,
                  letterSpacing: 1,
                  transition: "all 0.2s",
                }}
              >
                {loading ? "SCANNING..." : "↺ REFRESH"}
              </button>
              <div style={{
                marginTop: 8,
                fontSize: 11,
                fontFamily: "'JetBrains Mono', monospace",
                color: "#ffffff25",
              }}>
                {data ? (
                  <>
                    next scan in{" "}
                    <span style={{ color: "#4f8ef7" }}>{secLeft}s</span>
                    {" · "}
                    <span>{data.duration_ms}ms</span>
                  </>
                ) : "—"}
              </div>
              {data && (
                <div style={{ fontSize: 10, color: "#ffffff20", marginTop: 2, fontFamily: "'JetBrains Mono', monospace" }}>
                  {new Date(data.computed_at).toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Countdown bar */}
        <CountdownBar total={REFRESH_INTERVAL} elapsed={elapsed} />
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "0 32px 48px" }}>

        {/* Error state */}
        {error && (
          <div style={{
            marginTop: 32,
            padding: "16px 20px",
            background: "#ff525210",
            border: "1px solid #ff525230",
            borderRadius: 8,
            color: "#ff5252",
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
          }}>
            ⚠ {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !data && (
          <div style={{ marginTop: 48, textAlign: "center" }}>
            <div style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 13,
              color: "#4f8ef7",
              letterSpacing: 2,
            }}>
              {["FETCHING BARS", "COMPUTING RSI / MACD", "ASKING CLAUDE..."][
                Math.floor(Date.now() / 1500) % 3
              ]}
            </div>
            <div style={{
              marginTop: 16,
              display: "flex",
              justifyContent: "center",
              gap: 6,
            }}>
              {[0, 1, 2, 3, 4].map(i => (
                <div key={i} style={{
                  width: 4,
                  height: 4,
                  borderRadius: "50%",
                  background: "#4f8ef7",
                  animation: `pulse 1s ${i * 0.15}s infinite`,
                }} />
              ))}
            </div>
          </div>
        )}

        {/* Table */}
        {tickers.length > 0 && (
          <div className="fade-in" style={{
            marginTop: 24,
            background: "#0d0d1a",
            border: "1px solid #ffffff08",
            borderRadius: 12,
            overflow: "hidden",
          }}>
            {/* Stat bar */}
            <div style={{
              display: "flex",
              gap: 32,
              padding: "14px 24px",
              borderBottom: "1px solid #ffffff08",
              background: "#0a0a16",
            }}>
              {[
                { label: "Tickers", value: tickers.length },
                { label: "High conviction", value: tickers.filter(t => t.prob >= 0.65).length },
                { label: "Avg prob", value: (tickers.reduce((s, t) => s + t.prob, 0) / tickers.length * 100).toFixed(0) + "%" },
                { label: "Top pick", value: tickers[0]?.ticker || "—" },
              ].map(stat => (
                <div key={stat.label}>
                  <div style={{ fontSize: 10, color: "#ffffff30", letterSpacing: 1, textTransform: "uppercase" }}>
                    {stat.label}
                  </div>
                  <div style={{
                    fontSize: 16,
                    fontWeight: 700,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: "#f0f0ff",
                    marginTop: 2,
                  }}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr style={{ borderBottom: "1px solid #ffffff10" }}>
                    {["#", "Ticker", "Prob +10%", "Signals", "Change", "EMA Dist", "AI Rationale"].map(h => (
                      <th key={h} style={{
                        padding: "10px 16px",
                        textAlign: h === "#" ? "center" : "left",
                        fontSize: 10,
                        fontWeight: 600,
                        letterSpacing: 2,
                        textTransform: "uppercase",
                        color: "#ffffff30",
                        whiteSpace: "nowrap",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tickers.map((item, i) => (
                    <TickerRow
                      key={item.ticker}
                      item={item}
                      rank={i + 1}
                      isNew={isNew(item.ticker)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{
              padding: "12px 24px",
              borderTop: "1px solid #ffffff08",
              fontSize: 10,
              color: "#ffffff20",
              fontFamily: "'JetBrains Mono', monospace",
              display: "flex",
              justifyContent: "space-between",
            }}>
              <span>Features: RSI · MACD · EMA-21 · ATR · RVOL · 1D/5D momentum</span>
              <span>Not financial advice. For educational use only.</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
