import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type ISeriesMarkersPluginApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";
import { api } from "../lib/api";
import type { Asset, IntradayCandle, IntradaySignalsResponse, SwingSignal, OpeningRange, VolumeProfile, CandlePattern, RelativeStrengthData, MarketRegime, AnomalyScore, InsiderSentiment, PEADAnalysis, IntradayBacktest, IntradayAIAnalysis } from "../lib/types";

function PatternBadge({ p }: { p: CandlePattern }) {
  const color = p.type === "bullish" ? "#22c55e" : p.type === "bearish" ? "#ef4444" : "#f59e0b";
  const bg = p.type === "bullish" ? "rgba(34,197,94,0.08)" : p.type === "bearish" ? "rgba(239,68,68,0.08)" : "rgba(245,158,11,0.08)";
  const icon = p.type === "bullish" ? "▲" : p.type === "bearish" ? "▼" : "◆";
  const time = asUtcDate(p.timestamp).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });
  return (
    <div style={{ background: bg, border: `1px solid ${color}40`, borderRadius: 7, padding: "8px 12px", marginBottom: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
        <span style={{ color, fontSize: 11 }}>{icon}</span>
        <span style={{ color: "#e2e8f0", fontWeight: 700, fontSize: 12 }}>{p.name}</span>
        <span style={{ color: "#64748b", fontSize: 11, marginLeft: "auto" }}>{time}</span>
        <span style={{ color, fontSize: 11, fontWeight: 600 }}>{p.strength}%</span>
      </div>
      <div style={{ color: "#94a3b8", fontSize: 11 }}>{p.description}</div>
    </div>
  );
}

function InsiderBadge({ data, onSync, syncing, currency = "USD" }: { data: InsiderSentiment | null; onSync: () => void; syncing: boolean; currency?: string }) {
  if (!data) {
    return (
      <div style={{ background: "rgba(100,116,139,0.08)", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ color: "#64748b", fontSize: 12 }}>Brak danych insiderów</span>
          <button onClick={onSync} disabled={syncing} style={{ background: "#1e293b", border: "none", color: "#94a3b8", fontSize: 11, borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
            {syncing ? "..." : "Pobierz SEC"}
          </button>
        </div>
      </div>
    );
  }
  const color = data.signal === "bullish" ? "#22c55e" : data.signal === "bearish" ? "#ef4444" : "#64748b";
  const bg = data.signal === "bullish" ? "rgba(34,197,94,0.08)" : data.signal === "bearish" ? "rgba(239,68,68,0.08)" : "rgba(100,116,139,0.06)";
  const icon = data.signal === "bullish" ? "🟢" : data.signal === "bearish" ? "🔴" : "⚪";
  const fmt = (v: number) => fmtVolume(v, currency);
  return (
    <div style={{ background: bg, border: `1px solid ${color}30`, borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
        <span style={{ fontSize: 12 }}>{icon}</span>
        <span style={{ color, fontWeight: 700, fontSize: 12 }}>INSIDER {data.signal.toUpperCase()}</span>
        <span style={{ color: "#475569", fontSize: 10, marginLeft: "auto" }}>{data.days}d</span>
        <button onClick={onSync} disabled={syncing} style={{ background: "#1e293b", border: "none", color: "#64748b", fontSize: 10, borderRadius: 4, padding: "2px 6px", cursor: "pointer" }}>
          {syncing ? "..." : "↻"}
        </button>
      </div>
      <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 5 }}>{data.signal_description}</div>
      <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
        <span style={{ color: "#22c55e" }}>▲ {data.n_buys} buy {data.buy_value > 0 ? fmt(data.buy_value) : ""}</span>
        <span style={{ color: "#ef4444" }}>▼ {data.n_sells} sell {data.sell_value > 0 ? fmt(data.sell_value) : ""}</span>
      </div>
      {data.recent_trades.length > 0 && (
        <div style={{ marginTop: 6, borderTop: "1px solid #1e293b", paddingTop: 5 }}>
          {data.recent_trades.slice(0, 3).map((t, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#64748b", marginBottom: 1 }}>
              <span style={{ color: t.type === "buy" ? "#22c55e" : t.type === "sell" ? "#ef4444" : "#64748b", fontWeight: 600 }}>
                {t.type.toUpperCase()}
              </span>
              <span style={{ color: "#94a3b8", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</span>
              <span>{t.shares != null ? `${Math.abs(t.shares).toLocaleString()} szt` : ""}</span>
              <span>{t.date.slice(5)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AnomalyBadge({ data, onRefresh, refreshing }: { data: AnomalyScore | null; onRefresh: () => void; refreshing: boolean }) {
  if (!data) {
    return (
      <div style={{ background: "rgba(100,116,139,0.08)", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ color: "#64748b", fontSize: 12 }}>Brak danych anomalii</span>
          <button onClick={onRefresh} disabled={refreshing} style={{ background: "#1e293b", border: "none", color: "#94a3b8", fontSize: 11, borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
            {refreshing ? "..." : "Oblicz"}
          </button>
        </div>
      </div>
    );
  }
  const s = data.anomaly_score;
  const color = s >= 70 ? "#ef4444" : s >= 40 ? "#f59e0b" : "#22c55e";
  const bg = s >= 70 ? "rgba(239,68,68,0.10)" : s >= 40 ? "rgba(245,158,11,0.10)" : "rgba(34,197,94,0.08)";
  const label = s >= 70 ? "ANOMALIA" : s >= 40 ? "PODEJRZANY" : "NORMALNY";
  const icon = s >= 70 ? "🚨" : s >= 40 ? "⚠️" : "✓";
  const scored = asUtcDate(data.scored_at).toLocaleString("pl-PL", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", timeZone: "Europe/Warsaw" });
  return (
    <div style={{ background: bg, border: `1px solid ${color}40`, borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 13 }}>{icon}</span>
        <span style={{ color, fontWeight: 700, fontSize: 13 }}>{label}</span>
        <span style={{ color, fontSize: 18, fontWeight: 800, marginLeft: "auto" }}>{s.toFixed(0)}</span>
        <span style={{ color: "#64748b", fontSize: 11 }}>/100</span>
        <button onClick={onRefresh} disabled={refreshing} style={{ background: "#1e293b", border: "none", color: "#94a3b8", fontSize: 10, borderRadius: 4, padding: "2px 6px", cursor: "pointer", marginLeft: 4 }}>
          {refreshing ? "..." : "↻"}
        </button>
      </div>
      {data.top_features.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          {data.top_features.slice(0, 3).map((f) => (
            <div key={f.feature} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8", marginBottom: 2 }}>
              <span style={{ color: "#cbd5e1" }}>{f.feature}</span>
              <span>val={f.value.toFixed(2)} med={f.median.toFixed(2)} z={f.z_score.toFixed(1)}σ</span>
            </div>
          ))}
        </div>
      )}
      <div style={{ color: "#475569", fontSize: 10 }}>
        trenowany na {data.trained_on_rows} wierszach · {scored}
      </div>
    </div>
  );
}

function RegimeBadge({ regime }: { regime: MarketRegime }) {
  const cfg: Record<string, { label: string; color: string; bg: string; icon: string }> = {
    trend_up:   { label: "TREND ▲",      color: "#22c55e", bg: "rgba(34,197,94,0.12)",   icon: "📈" },
    trend_down: { label: "TREND ▼",      color: "#ef4444", bg: "rgba(239,68,68,0.12)",   icon: "📉" },
    range:      { label: "KONSOLIDACJA", color: "#f59e0b", bg: "rgba(245,158,11,0.12)",  icon: "↔" },
    volatile:   { label: "VOLATILE",     color: "#a78bfa", bg: "rgba(167,139,250,0.12)", icon: "⚡" },
    unknown:    { label: "BRAK DANYCH",  color: "#64748b", bg: "rgba(100,116,139,0.10)", icon: "?" },
  };
  const c = cfg[regime.regime] ?? cfg.unknown;
  return (
    <div style={{ background: c.bg, border: `1px solid ${c.color}40`, borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 15 }}>{c.icon}</span>
        <span style={{ color: c.color, fontWeight: 700, fontSize: 13 }}>{c.label}</span>
        {regime.adx !== null && (
          <span style={{ color: "#94a3b8", fontSize: 12, marginLeft: "auto" }}>ADX {regime.adx}</span>
        )}
      </div>
      <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: regime.bb_squeeze ? 4 : 0 }}>{regime.description}</div>
      {regime.adx !== null && regime.di_plus !== null && regime.di_minus !== null && (
        <div style={{ display: "flex", gap: 10, fontSize: 11 }}>
          <span style={{ color: "#22c55e" }}>+DI {regime.di_plus}</span>
          <span style={{ color: "#ef4444" }}>-DI {regime.di_minus}</span>
          {regime.bb_squeeze && <span style={{ color: "#f59e0b" }}>BB Squeeze</span>}
        </div>
      )}
    </div>
  );
}

function PEADBadge({ data }: { data: PEADAnalysis | null }) {
  if (!data || data.status === "no_data") {
    return (
      <div style={{ background: "rgba(100,116,139,0.08)", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px" }}>
        <span style={{ color: "#64748b", fontSize: 12 }}>PEAD — brak danych wynikowych</span>
      </div>
    );
  }
  const isActive = data.status === "active";
  const lbl = data.last_surprise_label;
  const driftColor = data.current_drift_pct != null
    ? (data.current_drift_pct > 0 ? "#22c55e" : "#ef4444")
    : "#94a3b8";
  const surpriseColor = lbl === "BEAT" ? "#22c55e" : lbl === "MISS" ? "#ef4444" : "#f59e0b";
  const reliabilityColor = data.reliability_pct != null
    ? (data.reliability_pct >= 65 ? "#22c55e" : data.reliability_pct >= 50 ? "#f59e0b" : "#ef4444")
    : "#64748b";
  const bg = isActive
    ? (lbl === "BEAT" ? "rgba(34,197,94,0.07)" : lbl === "MISS" ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)")
    : "rgba(100,116,139,0.06)";
  const border = isActive
    ? (lbl === "BEAT" ? "rgba(34,197,94,0.25)" : lbl === "MISS" ? "rgba(239,68,68,0.25)" : "rgba(245,158,11,0.25)")
    : "#1e293b";

  return (
    <div style={{ background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <span style={{ color: "#94a3b8", fontWeight: 700, fontSize: 11 }}>PEAD</span>
        {lbl && (
          <span style={{ color: surpriseColor, fontWeight: 700, fontSize: 12 }}>{lbl}</span>
        )}
        {data.last_eps_surprise_pct != null && (
          <span style={{ color: surpriseColor, fontSize: 11 }}>
            {data.last_eps_surprise_pct > 0 ? "+" : ""}{data.last_eps_surprise_pct.toFixed(1)}%
          </span>
        )}
        {data.current_drift_pct != null && (
          <span style={{ color: driftColor, fontWeight: 700, fontSize: 12, marginLeft: "auto" }}>
            {data.current_drift_pct > 0 ? "+" : ""}{data.current_drift_pct.toFixed(1)}%
          </span>
        )}
      </div>
      <div style={{ color: "#64748b", fontSize: 11, marginBottom: 5 }}>{data.status_description}</div>
      <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
        {data.reliability_pct != null && (
          <span style={{ color: reliabilityColor }}>
            niezawodność {data.reliability_pct.toFixed(0)}% ({data.n_events} zdarzeń)
          </span>
        )}
        {data.sue != null && (
          <span style={{ color: "#94a3b8" }}>SUE {data.sue > 0 ? "+" : ""}{data.sue.toFixed(1)}</span>
        )}
      </div>
      {data.events.length > 0 && (
        <div style={{ marginTop: 6, borderTop: "1px solid #1e293b", paddingTop: 5 }}>
          {data.events.slice(0, 3).map((ev, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#64748b", marginBottom: 1 }}>
              <span style={{ color: ev.surprise_label === "BEAT" ? "#22c55e" : ev.surprise_label === "MISS" ? "#ef4444" : "#f59e0b", fontWeight: 600 }}>
                {ev.surprise_label ?? "—"}
              </span>
              <span style={{ color: "#64748b" }}>{ev.report_date.slice(0, 7)}</span>
              <span style={{ color: ev.drift_5d != null && ev.drift_5d > 0 ? "#22c55e" : "#ef4444" }}>
                5d: {ev.drift_5d != null ? `${ev.drift_5d > 0 ? "+" : ""}${ev.drift_5d.toFixed(1)}%` : "—"}
              </span>
              {ev.aligned != null && (
                <span style={{ color: ev.aligned ? "#22c55e" : "#ef4444" }}>{ev.aligned ? "✓" : "✗"}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function fmtPrice(value: number, currency: string): string {
  return currency === "PLN" ? `${value.toFixed(2)} zł` : `$${value.toFixed(2)}`;
}

function fmtVolume(value: number, currency: string): string {
  const sym = currency === "PLN" ? "" : "$";
  const sfx = currency === "PLN" ? " zł" : "";
  if (value >= 1e6) return `${sym}${(value / 1e6).toFixed(1)}M${sfx}`;
  if (value >= 1e3) return `${sym}${(value / 1e3).toFixed(0)}K${sfx}`;
  return `${sym}${value.toFixed(0)}${sfx}`;
}

type Indicators = { ema9: boolean; ema20: boolean; bb: boolean; vwap: boolean; or: boolean; poc: boolean; va: boolean; sr: boolean };

const IND_META: Record<keyof Indicators, { label: string; color: string; tooltip: string }> = {
  ema9:  { label: "EMA9",  color: "#f59e0b", tooltip: "EMA 9 — średnia wykładnicza z 9 świec. Szybka linia trendu, sygnalizuje krótkoterminowy kierunek." },
  ema20: { label: "EMA20", color: "#818cf8", tooltip: "EMA 20 — średnia wykładnicza z 20 świec. Wolniejsza linia trendu; przecięcie EMA9/EMA20 = sygnał wejścia." },
  bb:    { label: "BB",    color: "#475569", tooltip: "Wstęgi Bollingera (20, 2σ) — górna i dolna krawędź to statystyczne ekstremum. Wyjście poza wstęgę = potencjalny sygnał zwrotu." },
  vwap:  { label: "VWAP", color: "#f472b6", tooltip: "VWAP — średnia cena ważona wolumenem, resetowana każdego dnia. Instytucje kupują poniżej VWAP, sprzedają powyżej." },
  or:    { label: "OR",    color: "#fb923c", tooltip: "Opening Range — zakres cenowy z pierwszych 30 minut sesji. Wybicie ORH/ORL to często silny sygnał kierunkowy." },
  poc:   { label: "POC",  color: "#fbbf24", tooltip: "Point of Control — poziom ceny z największym wolumenem na sesji. Cena wraca do POC jak do 'sprawiedliwej wartości'." },
  va:    { label: "VA",   color: "#a78bfa", tooltip: "Value Area (VAH/VAL) — 70% wolumenu sesji mieści się w tym zakresie. Wejście/wyjście z VA to kluczowe poziomy." },
  sr:    { label: "S/R",  color: "#94a3b8", tooltip: "Wsparcia i Opory — lokalne minima/maksima cenowe. Cena często zatrzymuje się lub odbija przy tych poziomach." },
};

function IndToggle({ id, ind, setInd }: { id: keyof Indicators; ind: Indicators; setInd: React.Dispatch<React.SetStateAction<Indicators>> }) {
  const { label, color, tooltip } = IND_META[id];
  const active = ind[id];
  return (
    <button
      title={tooltip}
      onClick={() => setInd(prev => ({ ...prev, [id]: !prev[id] }))}
      style={{
        background: active ? `${color}22` : "transparent",
        border: `1px solid ${active ? color : "#334155"}`,
        color: active ? color : "#475569",
        borderRadius: 4, padding: "2px 8px", fontSize: 11, cursor: "pointer",
        textDecoration: active ? "none" : "line-through",
        userSelect: "none",
      }}
    >
      {label}
    </button>
  );
}

function BuySellBanner({ signals, currency = "USD" }: { signals: IntradaySignalsResponse | null; currency?: string }) {
  if (!signals || signals.candles_count < 30) return null;
  const buys  = signals.signals.filter(s => s.type === "BUY");
  const sells = signals.signals.filter(s => s.type === "SELL");
  const bestBuy  = buys.length  ? buys.reduce((a, b)  => a.strength >= b.strength ? a : b)  : null;
  const bestSell = sells.length ? sells.reduce((a, b) => a.strength >= b.strength ? a : b) : null;

  let sig: "BUY" | "SELL" | "WAIT" = "WAIT";
  let best = bestBuy;
  if (bestBuy && (!bestSell || bestBuy.strength >= bestSell.strength)) { sig = "BUY"; best = bestBuy; }
  else if (bestSell && (!bestBuy || bestSell.strength > bestBuy.strength)) { sig = "SELL"; best = bestSell; }

  if (sig === "WAIT" || !best) {
    return (
      <div style={{ background: "rgba(100,116,139,0.10)", border: "1px solid #334155", borderRadius: 8, padding: "9px 14px", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "#475569", fontSize: 16 }}>⏸</span>
          <span style={{ color: "#64748b", fontWeight: 700, fontSize: 13 }}>CZEKAJ</span>
          <span style={{ color: "#334155", fontSize: 11, marginLeft: "auto" }}>brak aktywnego sygnału</span>
        </div>
      </div>
    );
  }

  const isBuy = sig === "BUY";
  const color = isBuy ? "#22c55e" : "#ef4444";
  const bg    = isBuy ? "rgba(34,197,94,0.13)"  : "rgba(239,68,68,0.13)";
  return (
    <div style={{ background: bg, border: `2px solid ${color}`, borderRadius: 8, padding: "9px 14px", marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: best.reasons.length ? 5 : 0 }}>
        <span style={{ color, fontSize: 18, fontWeight: 900, lineHeight: 1 }}>{isBuy ? "▲" : "▼"}</span>
        <span style={{ color, fontWeight: 900, fontSize: 15, letterSpacing: "0.4px" }}>{isBuy ? "KUP TERAZ" : "SPRZEDAJ TERAZ"}</span>
        <span style={{ color: "#e2e8f0", fontWeight: 700, fontSize: 13 }}>{fmtPrice(best.price, currency)}</span>
        <span style={{ background: `${color}33`, color, fontWeight: 700, fontSize: 11, borderRadius: 4, padding: "1px 7px", marginLeft: "auto" }}>
          siła {best.strength}%
        </span>
      </div>
      {best.reasons.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
          {best.reasons.slice(0, 4).map((r, i) => (
            <span key={i} style={{ background: "#1e293b", color: "#94a3b8", fontSize: 10, borderRadius: 3, padding: "1px 6px" }}>{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

type Resolution = "5" | "15" | "60";

const DARK_CHART_OPTIONS = {
  layout: {
    background: { color: "#0f172a" },
    textColor: "#94a3b8",
    fontFamily: "Inter, sans-serif",
  },
  grid: {
    vertLines: { color: "#1e293b" },
    horzLines: { color: "#1e293b" },
  },
  crosshair: { mode: 0 },
  rightPriceScale: { borderColor: "#334155" },
  timeScale: { borderColor: "#334155", timeVisible: true, secondsVisible: false },
};

const AUTO_REFRESH_SEC = 120;

function asUtcDate(iso: string): Date {
  // Backend returns naive UTC strings without Z — append Z so browser doesn't treat as local time
  return new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
}

function toTimestamp(iso: string): Time {
  const d = asUtcDate(iso);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Warsaw",
    year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric",
    hour12: false,
  }).formatToParts(d);
  const get = (type: string) => parseInt(parts.find(p => p.type === type)?.value ?? "0");
  return (Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second")) / 1000) as Time;
}

function SignalBadge({ signal, currency = "USD" }: { signal: SwingSignal; currency?: string }) {
  const isBuy = signal.type === "BUY";
  const color = isBuy ? "#22c55e" : "#ef4444";
  const bg = isBuy ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)";
  const time = asUtcDate(signal.timestamp).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });
  return (
    <div style={{ background: bg, border: `1px solid ${color}`, borderRadius: 8, padding: "10px 14px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ color, fontWeight: 700, fontSize: 13 }}>{signal.type}</span>
        <span style={{ color: "#94a3b8", fontSize: 12 }}>{time}</span>
        <span style={{ color: "#e2e8f0", fontSize: 13, marginLeft: "auto" }}>{fmtPrice(signal.price, currency)}</span>
        <span style={{ color, fontSize: 12, fontWeight: 600 }}>siła {signal.strength}%</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {signal.reasons.map((r, i) => (
          <span key={i} style={{ background: "#1e293b", color: "#cbd5e1", fontSize: 11, borderRadius: 4, padding: "2px 7px" }}>
            {r}
          </span>
        ))}
      </div>
    </div>
  );
}

function BacktestPanel({
  backtest,
  running,
  onRun,
}: {
  backtest: IntradayBacktest | null;
  running: boolean;
  onRun: () => void;
}) {
  const pct = (v: number | null, decimals = 1) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;
  const num = (v: number | null) => (v == null ? "—" : v.toFixed(0));
  const fmtDate = (iso: string) =>
    new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" });

  return (
    <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 14 }}>
          Backtest &amp; Kalibracja
        </span>
        <button
          onClick={onRun}
          disabled={running}
          style={{
            padding: "3px 10px", fontSize: 11, borderRadius: 5, cursor: running ? "default" : "pointer",
            background: running ? "#334155" : "#6366f1", color: "#fff", border: "none", fontWeight: 600,
          }}
        >
          {running ? "Trwa…" : backtest ? "Odśwież" : "Uruchom"}
        </button>
      </div>

      {!backtest ? (
        <div style={{ color: "#475569", fontSize: 13 }}>
          Kliknij „Uruchom" aby przeprowadzić backtest i skalibrować progi sygnałów.
        </div>
      ) : (
        <>
          {/* Calibrated thresholds */}
          <div style={{ background: "#1e293b", borderRadius: 7, padding: "8px 12px", marginBottom: 10 }}>
            <div style={{ color: "#6366f1", fontSize: 11, fontWeight: 700, marginBottom: 6, letterSpacing: "0.05em" }}>
              SKALIBROWANE PROGI
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", fontSize: 12 }}>
              <span style={{ color: "#94a3b8" }}>RSI kupno &lt;</span>
              <span style={{ color: "#22c55e", fontWeight: 600 }}>{backtest.calibrated.rsi_oversold}</span>
              <span style={{ color: "#94a3b8" }}>RSI sprzedaż &gt;</span>
              <span style={{ color: "#ef4444", fontWeight: 600 }}>{backtest.calibrated.rsi_overbought}</span>
              <span style={{ color: "#94a3b8" }}>Stop Loss</span>
              <span style={{ color: "#ef4444", fontWeight: 600 }}>{backtest.calibrated.sl_pct}%</span>
              <span style={{ color: "#94a3b8" }}>Take Profit</span>
              <span style={{ color: "#22c55e", fontWeight: 600 }}>{backtest.calibrated.tp_pct}%</span>
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 10px", marginBottom: 10 }}>
            {[
              ["Transakcje", num(backtest.total_signals), "#e2e8f0"],
              ["Trafność", backtest.win_rate != null ? `${(backtest.win_rate * 100).toFixed(0)}%` : "—",
                backtest.win_rate != null && backtest.win_rate >= 0.5 ? "#22c55e" : "#ef4444"],
              ["Śr. zysk", pct(backtest.avg_win_pct, 2), "#22c55e"],
              ["Śr. strata", pct(backtest.avg_loss_pct, 2), "#ef4444"],
              ["Avg zwrot", pct(backtest.avg_return_pct, 2),
                backtest.avg_return_pct != null && backtest.avg_return_pct >= 0 ? "#22c55e" : "#ef4444"],
              ["Expectancy", pct(backtest.expectancy, 2),
                backtest.expectancy != null && backtest.expectancy >= 0 ? "#22c55e" : "#ef4444"],
            ].map(([label, value, color]) => (
              <div key={label as string} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "#64748b", fontSize: 11 }}>{label}</span>
                <span style={{ color: color as string, fontSize: 12, fontWeight: 600 }}>{value}</span>
              </div>
            ))}
          </div>

          {/* Baseline comparison */}
          {backtest.default.total_signals > 0 && (
            <div style={{ fontSize: 11, color: "#475569", marginBottom: 8, padding: "5px 8px", background: "#0f172a", borderRadius: 5, border: "1px solid #1e293b" }}>
              Domyślne progi (RSI 32/68, SL 1.5%, TP 2%):&nbsp;
              <span style={{ color: "#94a3b8" }}>{backtest.default.total_signals} tr. · </span>
              <span style={{ color: backtest.default.win_rate != null && backtest.default.win_rate >= 0.5 ? "#22c55e" : "#ef4444" }}>
                {backtest.default.win_rate != null ? `${(backtest.default.win_rate * 100).toFixed(0)}% traf.` : "—"}
              </span>
              &nbsp;·&nbsp;
              <span style={{ color: backtest.default.expectancy != null && backtest.default.expectancy >= 0 ? "#22c55e" : "#ef4444" }}>
                {pct(backtest.default.expectancy, 2)} exp.
              </span>
            </div>
          )}

          {/* Last trades */}
          {backtest.trades.length > 0 && (
            <div>
              <div style={{ color: "#475569", fontSize: 11, marginBottom: 4 }}>
                Ostatnie transakcje · {backtest.lookback_days}d · {backtest.candles_count} świec · {fmtDate(backtest.run_at)}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {[...backtest.trades].reverse().slice(0, 8).map((t, i) => (
                  <div key={i} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11 }}>
                    <span style={{ color: t.direction === "BUY" ? "#22c55e" : "#ef4444", fontWeight: 700, width: 32 }}>
                      {t.direction === "BUY" ? "▲" : "▼"} {t.direction === "BUY" ? "L" : "S"}
                    </span>
                    <span style={{ color: t.result === "TP" ? "#22c55e" : t.result === "SL" ? "#ef4444" : "#f59e0b", fontWeight: 600, width: 52 }}>
                      {t.result}
                    </span>
                    <span style={{ color: t.pct >= 0 ? "#22c55e" : "#ef4444", fontWeight: 600, width: 52 }}>
                      {t.pct >= 0 ? "+" : ""}{t.pct.toFixed(2)}%
                    </span>
                    <span style={{ color: "#475569" }}>{t.bars_held}b</span>
                    <span style={{ color: "#334155", marginLeft: "auto" }}>
                      {new Date(t.timestamp.endsWith("Z") ? t.timestamp : t.timestamp + "Z")
                        .toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit" })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AIAnalysisPanel({
  analysis,
  running,
  onRun,
}: {
  analysis: IntradayAIAnalysis | null;
  running: boolean;
  onRun: () => void;
}) {
  const decyzjaColor = analysis?.decyzja === "KUP" ? "#22c55e" : analysis?.decyzja === "SPRZEDAJ" ? "#ef4444" : "#f59e0b";
  const decyzjaBg = analysis?.decyzja === "KUP" ? "rgba(34,197,94,0.08)" : analysis?.decyzja === "SPRZEDAJ" ? "rgba(239,68,68,0.08)" : "rgba(245,158,11,0.08)";
  const decyzjaIcon = analysis?.decyzja === "KUP" ? "▲" : analysis?.decyzja === "SPRZEDAJ" ? "▼" : "◆";

  return (
    <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 14 }}>Analiza AI</div>
        <button
          onClick={onRun}
          disabled={running}
          style={{
            background: running ? "#1e293b" : "rgba(99,102,241,0.15)",
            border: "1px solid rgba(99,102,241,0.4)",
            color: running ? "#475569" : "#a5b4fc",
            fontSize: 12,
            borderRadius: 6,
            padding: "4px 12px",
            cursor: running ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {running ? "Analizuje…" : analysis ? "Odśwież" : "Zapytaj AI"}
        </button>
      </div>

      {!analysis ? (
        <div style={{ color: "#475569", fontSize: 12 }}>
          Kliknij „Zapytaj AI" aby uzyskać holograficzną analizę wszystkich sygnałów przez Claude.
        </div>
      ) : (
        <>
          <div style={{ background: decyzjaBg, border: `1px solid ${decyzjaColor}40`, borderRadius: 8, padding: "10px 14px", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ color: decyzjaColor, fontSize: 18, fontWeight: 700 }}>{decyzjaIcon} {analysis.decyzja}</span>
              <span style={{ color: "#64748b", fontSize: 12, marginLeft: "auto" }}>pewność {analysis.pewnosc}%</span>
            </div>
            <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5 }}>{analysis.uzasadnienie}</div>
          </div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ color: "#64748b", fontSize: 11, fontWeight: 600, marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>Argumenty</div>
            {analysis.kluczowe_argumenty.map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 6, marginBottom: 3 }}>
                <span style={{ color: decyzjaColor, fontSize: 10, marginTop: 2 }}>●</span>
                <span style={{ color: "#94a3b8", fontSize: 12 }}>{a}</span>
              </div>
            ))}
          </div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ color: "#64748b", fontSize: 11, fontWeight: 600, marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>Ryzyka</div>
            {analysis.ryzyka.map((r, i) => (
              <div key={i} style={{ display: "flex", gap: 6, marginBottom: 3 }}>
                <span style={{ color: "#f59e0b", fontSize: 10, marginTop: 2 }}>▲</span>
                <span style={{ color: "#94a3b8", fontSize: 12 }}>{r}</span>
              </div>
            ))}
          </div>

          {(analysis.poziomy.wejscie || analysis.poziomy.stop_loss || analysis.poziomy.take_profit) && (
            <div style={{ background: "rgba(15,23,42,0.8)", borderRadius: 6, border: "1px solid #1e293b", padding: "8px 12px", marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                {analysis.poziomy.wejscie != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ color: "#64748b", fontSize: 10 }}>Wejście</div>
                    <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 600 }}>{analysis.poziomy.wejscie}</div>
                  </div>
                )}
                {analysis.poziomy.stop_loss != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ color: "#64748b", fontSize: 10 }}>Stop Loss</div>
                    <div style={{ color: "#ef4444", fontSize: 13, fontWeight: 600 }}>{analysis.poziomy.stop_loss}</div>
                  </div>
                )}
                {analysis.poziomy.take_profit != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ color: "#64748b", fontSize: 10 }}>Take Profit</div>
                    <div style={{ color: "#22c55e", fontSize: 13, fontWeight: 600 }}>{analysis.poziomy.take_profit}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#475569", fontSize: 11 }}>Horyzont: <span style={{ color: "#94a3b8" }}>{analysis.horyzont}</span></span>
            {analysis._cached && <span style={{ color: "#334155", fontSize: 10 }}>⚡ cached</span>}
          </div>
        </>
      )}
    </div>
  );
}

interface Props {
  assets: Asset[];
  selectedAssetId: string;
}

export function IntradayTab({ assets, selectedAssetId }: Props) {
  const stocks = assets.filter((a) => a.type === "stock");

  const selectedId = stocks.some((s) => s.id === selectedAssetId) ? selectedAssetId : (stocks[0]?.id ?? "");
  const asset = assets.find((a) => a.id === selectedId);
  const [resolution, setResolution] = useState<Resolution>("15");
  const [timeRange, setTimeRange] = useState<"1d" | "2d" | "5d" | "all">("all");
  const [candles, setCandles] = useState<IntradayCandle[]>([]);
  const [signals, setSignals] = useState<IntradaySignalsResponse | null>(null);
  const [rsData, setRsData] = useState<RelativeStrengthData | null>(null);
  const [anomaly, setAnomaly] = useState<AnomalyScore | null>(null);
  const [anomalyRefreshing, setAnomalyRefreshing] = useState(false);
  const [insider, setInsider] = useState<InsiderSentiment | null>(null);
  const [insiderSyncing, setInsiderSyncing] = useState(false);
  const [pead, setPead] = useState<PEADAnalysis | null>(null);
  const [backtest, setBacktest] = useState<IntradayBacktest | null>(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const aiAnalysisMapRef = useRef<Map<string, IntradayAIAnalysis>>(new Map());
  const [aiAnalysis, setAiAnalysis] = useState<IntradayAIAnalysis | null>(null);
  const [aiAnalysisRunning, setAiAnalysisRunning] = useState(false);
  const [ind, setInd] = useState<Indicators>({ ema9: true, ema20: true, bb: true, vwap: true, or: true, poc: true, va: true, sr: true });
  const indRef = useRef<Indicators>({ ema9: true, ema20: true, bb: true, vwap: true, or: true, poc: true, va: true, sr: true });
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefreshCountdown, setAutoRefreshCountdown] = useState(AUTO_REFRESH_SEC);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const volumeContainerRef = useRef<HTMLDivElement>(null);
  const rsContainerRef = useRef<HTMLDivElement>(null);
  const vpvrCanvasRef = useRef<HTMLCanvasElement>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const volumeChartRef = useRef<IChartApi | null>(null);
  const rsChartRef = useRef<IChartApi | null>(null);

  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema9Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const vwapRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const srPriceLinesRef  = useRef<IPriceLine[]>([]);
  const orPriceLinesRef  = useRef<IPriceLine[]>([]);
  const pocPriceLinesRef = useRef<IPriceLine[]>([]);
  const vaPriceLinesRef  = useRef<IPriceLine[]>([]);
  type PLData = { sr: { level: number; type: "support" | "resistance" }[]; or: OpeningRange | null; poc: number | null; va: { vah: number; val: number } | null };
  const plDataRef = useRef<PLData>({ sr: [], or: null, poc: null, va: null });
  const vpDataRef = useRef<VolumeProfile | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lastCandleIsoRef = useRef<string | null>(null);
  const resolutionRef = useRef<Resolution>("15");
  const candlesCountRef = useRef<number>(0);

  const drawVPVR = useCallback(() => {
    const canvas = vpvrCanvasRef.current;
    const series = candleSeriesRef.current;
    const container = chartContainerRef.current;
    const vpData = vpDataRef.current;
    if (!canvas || !series || !container || !vpData || !vpData.bins.length) return;

    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth;
    const h = 340;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(dpr, dpr);

    const BAR_MAX_W = Math.round(w * 0.18);
    const RIGHT_PAD = 60; // szerokość osi ceny po prawej

    for (const bin of vpData.bins) {
      const yCenter = series.priceToCoordinate(bin.price);
      if (yCenter == null || yCenter < 0 || yCenter > h) continue;

      const binSize = (vpData.price_high - vpData.price_low) / vpData.bins.length;
      const yNext = series.priceToCoordinate(bin.price + binSize / 2);
      const yPrev = series.priceToCoordinate(bin.price - binSize / 2);
      const halfH = Math.max(
        1,
        Math.round(Math.abs((yNext ?? yCenter + 3) - (yPrev ?? yCenter - 3)) / 2) - 1
      );

      const barW = Math.round((bin.pct / 100) * BAR_MAX_W);
      const x = w - RIGHT_PAD - barW;

      if (bin.is_poc && indRef.current.poc) {
        ctx.fillStyle = "rgba(251,191,36,0.85)";
      } else if (bin.in_va && indRef.current.va) {
        ctx.fillStyle = "rgba(99,102,241,0.45)";
      } else {
        ctx.fillStyle = "rgba(100,116,139,0.25)";
      }
      ctx.fillRect(x, yCenter - halfH, barW, halfH * 2);
    }
    ctx.resetTransform();
  }, []);

  const _rebuildPriceLines = useCallback(() => {
    const cs = candleSeriesRef.current;
    if (!cs) return;
    const cur = indRef.current;
    const data = plDataRef.current;

    const allRefs = [...srPriceLinesRef.current, ...orPriceLinesRef.current, ...pocPriceLinesRef.current, ...vaPriceLinesRef.current];
    allRefs.forEach(pl => { try { cs.removePriceLine(pl); } catch { /* stale */ } });
    srPriceLinesRef.current = []; orPriceLinesRef.current = []; pocPriceLinesRef.current = []; vaPriceLinesRef.current = [];

    if (cur.sr) {
      data.sr.forEach(({ level, type }) => {
        const pl = cs.createPriceLine({ price: level, color: type === "support" ? "#22c55e" : "#ef4444", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `${type === "support" ? "S" : "R"} ${level.toFixed(2)}` });
        srPriceLinesRef.current.push(pl);
      });
    }
    if (cur.or && data.or) {
      if (data.or.high) { const pl = cs.createPriceLine({ price: data.or.high, color: "#fb923c", lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `ORH ${data.or.high.toFixed(2)}` }); orPriceLinesRef.current.push(pl); }
      if (data.or.low)  { const pl = cs.createPriceLine({ price: data.or.low,  color: "#fb923c", lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `ORL ${data.or.low.toFixed(2)}`  }); orPriceLinesRef.current.push(pl); }
    }
    if (cur.poc && data.poc != null) {
      const pl = cs.createPriceLine({ price: data.poc, color: "#fbbf24", lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `POC ${data.poc.toFixed(2)}` });
      pocPriceLinesRef.current.push(pl);
    }
    if (cur.va && data.va) {
      if (data.va.vah) { const pl = cs.createPriceLine({ price: data.va.vah, color: "#a78bfa", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `VAH ${data.va.vah.toFixed(2)}` }); vaPriceLinesRef.current.push(pl); }
      if (data.va.val) { const pl = cs.createPriceLine({ price: data.va.val, color: "#a78bfa", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `VAL ${data.va.val.toFixed(2)}` }); vaPriceLinesRef.current.push(pl); }
    }
  }, []);

  useEffect(() => {
    if (!chartContainerRef.current || !rsiContainerRef.current || !volumeContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      ...DARK_CHART_OPTIONS,
      height: 340,
      width: chartContainerRef.current.clientWidth,
    });
    chartRef.current = chart;

    candleSeriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    markersPluginRef.current = createSeriesMarkers(candleSeriesRef.current, []);

    ema9Ref.current = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    ema20Ref.current = chart.addSeries(LineSeries, { color: "#818cf8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    bbUpperRef.current = chart.addSeries(LineSeries, { color: "#475569", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
    bbLowerRef.current = chart.addSeries(LineSeries, { color: "#475569", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
    vwapRef.current = chart.addSeries(LineSeries, { color: "#f472b6", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });

    const SUB_CHART_TIME_SCALE = { ...DARK_CHART_OPTIONS.timeScale, visible: false };

    const rsiChart = createChart(rsiContainerRef.current, {
      ...DARK_CHART_OPTIONS,
      height: 100,
      width: rsiContainerRef.current.clientWidth,
      timeScale: SUB_CHART_TIME_SCALE,
    });
    rsiChartRef.current = rsiChart;
    rsiSeriesRef.current = rsiChart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });

    const volChart = createChart(volumeContainerRef.current, {
      ...DARK_CHART_OPTIONS,
      height: 80,
      width: volumeContainerRef.current.clientWidth,
      timeScale: SUB_CHART_TIME_SCALE,
    });
    volumeChartRef.current = volChart;
    volumeSeriesRef.current = volChart.addSeries(HistogramSeries, {
      color: "#334155",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    const rsChart = createChart(rsContainerRef.current!, {
      ...DARK_CHART_OPTIONS,
      height: 80,
      width: rsContainerRef.current!.clientWidth,
    });
    rsChartRef.current = rsChart;
    rsSeriesRef.current = rsChart.addSeries(HistogramSeries, {
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      priceScaleId: "rs",
    });

    // Bidirectional sync — lock prevents infinite loops
    let syncing = false;
    const allCharts = [chart, rsiChart, volChart, rsChart];
    allCharts.forEach(source => {
      source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        allCharts.forEach(target => {
          if (target !== source) target.timeScale().setVisibleLogicalRange(range);
        });
        syncing = false;
        drawVPVR();
      });
    });

    chart.priceScale("right").applyOptions({});
    chart.subscribeCrosshairMove(() => drawVPVR());

    const ro = new ResizeObserver(() => {
      if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      if (rsiContainerRef.current) rsiChart.applyOptions({ width: rsiContainerRef.current.clientWidth });
      if (volumeContainerRef.current) volChart.applyOptions({ width: volumeContainerRef.current.clientWidth });
      if (rsContainerRef.current) rsChart.applyOptions({ width: rsContainerRef.current.clientWidth });
      drawVPVR();
    });
    if (chartContainerRef.current) ro.observe(chartContainerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      rsiChart.remove();
      volChart.remove();
      rsChart.remove();
    };
  }, [drawVPVR]);

  const timeRangeRef = useRef<"1d" | "2d" | "5d" | "all">("all");
  useEffect(() => { timeRangeRef.current = timeRange; }, [timeRange]);
  useEffect(() => { resolutionRef.current = resolution; }, [resolution]);

  const applyTimeRange = useCallback((range: "1d" | "2d" | "5d" | "all") => {
    const allCharts = [chartRef.current, rsiChartRef.current, volumeChartRef.current, rsChartRef.current];
    if (range === "all") {
      allCharts.forEach(c => c?.timeScale().fitContent());
      return;
    }
    const total = candlesCountRef.current;
    if (total === 0) return;

    const days = range === "1d" ? 1 : range === "2d" ? 2 : 5;
    const res = resolutionRef.current;
    // 390 min = typowa sesja NYSE (9:30-16:00)
    const barsPerDay = Math.ceil(390 / parseInt(res));
    const barsToShow = days * barsPerDay;

    // Logical range: indeksy świec (0 = pierwsza, total-1 = ostatnia)
    // Dodajemy +3 bary prawego marginesu żeby ostatnia świeca nie była przy samej krawędzi
    const to = total - 1 + 3;
    const from = to - barsToShow;

    allCharts.forEach(c => { try { c?.timeScale().setVisibleLogicalRange({ from, to }); } catch {} });
  }, []);

  const loadData = useCallback(async (assetId: string, res: Resolution) => {
    if (!assetId) return;
    setLoading(true);
    setError(null);
    try {
      const full = await api.intradayFull(assetId, res);
      const c = full.candles;
      const s = full.signals;
      const vpResult = full.volume_profile;
      const rs = full.relative_strength;
      setCandles(c);
      setSignals(s);
      setRsData(rs);
      setAnomaly(full.anomaly);
      setInsider(full.insider);
      setPead(full.pead);
      vpDataRef.current = vpResult;
      lastCandleIsoRef.current = c.length > 0 ? c[c.length - 1].timestamp : null;
      candlesCountRef.current = c.length;
      api.intradayBacktest(assetId, res).then(setBacktest).catch(() => {});
      setLastRefresh(new Date());
      setAutoRefreshCountdown(AUTO_REFRESH_SEC);

      if (candleSeriesRef.current && c.length > 0) {
        const candleData: CandlestickData[] = c.map((x) => ({
          time: toTimestamp(x.timestamp), open: x.open, high: x.high, low: x.low, close: x.close,
        }));
        candleSeriesRef.current.setData(candleData);

        ema9Ref.current?.setData(c.filter((x) => x.ema9 != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.ema9! })));
        ema20Ref.current?.setData(c.filter((x) => x.ema20 != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.ema20! })));
        bbUpperRef.current?.setData(c.filter((x) => x.bb_upper != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.bb_upper! })));
        bbLowerRef.current?.setData(c.filter((x) => x.bb_lower != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.bb_lower! })));
        vwapRef.current?.setData(c.filter((x) => x.vwap != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.vwap! })));

        rsiSeriesRef.current?.setData(c.filter((x) => x.rsi != null).map((x): LineData => ({ time: toTimestamp(x.timestamp), value: x.rsi! })));

        volumeSeriesRef.current?.setData(c.map((x): HistogramData => ({
          time: toTimestamp(x.timestamp),
          value: x.volume,
          color: x.close >= x.open ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
        })));

        applyTimeRange(timeRangeRef.current);

        // Store price-line data and rebuild respecting indicator toggles
        const or = s?.opening_range as OpeningRange | undefined;
        plDataRef.current = {
          sr: [
            ...(s?.support ?? []).map(l => ({ level: l, type: "support" as const })),
            ...(s?.resistance ?? []).map(l => ({ level: l, type: "resistance" as const })),
          ],
          or: or?.high != null ? or : null,
          poc: vpResult?.poc ?? null,
          va: vpResult?.vah != null && vpResult?.val != null ? { vah: vpResult.vah, val: vpResult.val } : null,
        };
        _rebuildPriceLines();
        // Markery formacji świecowych
        if (markersPluginRef.current) {
          const markers = (s?.patterns ?? []).map((p) => ({
            time: toTimestamp(p.timestamp),
            position: p.type === "bullish" ? "belowBar" as const : p.type === "bearish" ? "aboveBar" as const : "inBar" as const,
            color: p.type === "bullish" ? "#22c55e" : p.type === "bearish" ? "#ef4444" : "#f59e0b",
            shape: p.type === "bullish" ? "arrowUp" as const : p.type === "bearish" ? "arrowDown" as const : "circle" as const,
            text: p.name,
          }));
          markersPluginRef.current.setMarkers(markers);
        }
        // RS vs QQQ histogram
        if (rsSeriesRef.current && rs?.data?.length) {
          rsSeriesRef.current.setData(rs.data.map((pt): HistogramData => ({
            time: toTimestamp(pt.timestamp),
            value: pt.rs,
            color: pt.rs >= 0 ? "rgba(34,197,94,0.7)" : "rgba(239,68,68,0.7)",
          })));
        }
        // Rysuj VPVR po załadowaniu świec
        requestAnimationFrame(() => drawVPVR());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd ładowania danych");
    } finally {
      setLoading(false);
    }
  }, [_rebuildPriceLines]);

  useEffect(() => {
    loadData(selectedId, resolution);
  }, [selectedId, resolution, loadData]);

  useEffect(() => {
    setAiAnalysis(aiAnalysisMapRef.current.get(selectedId) ?? null);
  }, [selectedId]);

  useEffect(() => {
    const currency = asset?.currency ?? "USD";
    const fmt = (price: number) => fmtPrice(price, currency);
    try { chartRef.current?.applyOptions({ localization: { priceFormatter: fmt } }); } catch { /* v5 może nie wspierać */ }
  }, [asset?.currency]);


  // Auto-refresh co AUTO_REFRESH_SEC sekund — podczas godzin handlowych też syncuje
  useEffect(() => {
    const interval = setInterval(() => {
      setAutoRefreshCountdown((prev) => {
        if (prev <= 1) {
          const now = new Date();
          const h = now.getHours(), m = now.getMinutes();
          const minutes = h * 60 + m;
          const isMarketHours = now.getDay() >= 1 && now.getDay() <= 5 && minutes >= 9 * 60 && minutes <= 22 * 60 + 15;
          if (isMarketHours && selectedId) {
            api.intradaySync(selectedId, resolution).catch(() => null).finally(() => loadData(selectedId, resolution));
          } else {
            loadData(selectedId, resolution);
          }
          return AUTO_REFRESH_SEC;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [selectedId, resolution, loadData]);

  // Synchronize ind state with indRef and apply series/price-line visibility
  useEffect(() => {
    indRef.current = ind;
    ema9Ref.current?.applyOptions({ visible: ind.ema9 });
    ema20Ref.current?.applyOptions({ visible: ind.ema20 });
    bbUpperRef.current?.applyOptions({ visible: ind.bb });
    bbLowerRef.current?.applyOptions({ visible: ind.bb });
    vwapRef.current?.applyOptions({ visible: ind.vwap });
    _rebuildPriceLines();
    requestAnimationFrame(() => drawVPVR());
  }, [ind, _rebuildPriceLines, drawVPVR]);

  const handleSync = async () => {
    if (!selectedId) return;
    setSyncing(true);
    setError(null);
    try {
      const result = await api.intradaySync(selectedId, resolution);
      await loadData(selectedId, resolution);
      if (result.new_candles === 0) {
        if (result.fetched_from_api === 0) {
          setError("Finnhub nie zwrócił danych — rynek może być zamknięty lub brak danych dla tego symbolu");
        } else {
          setError(`Dane aktualne — ${result.fetched_from_api} świec z API, wszystkie już w bazie`);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd sync");
    } finally {
      setSyncing(false);
    }
  };

  const latestCandle = candles[candles.length - 1];
  const or = signals?.opening_range as OpeningRange | undefined;
  const orActive = or && or.high != null;

  return (
    <div style={{ padding: "0 16px 32px" }}>
      {/* Toolbar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {(["5", "15", "60"] as Resolution[]).map((r) => (
            <button
              key={r}
              onClick={() => setResolution(r)}
              style={{
                background: resolution === r ? "#6366f1" : "#1e293b",
                color: "#e2e8f0", border: "none", borderRadius: 6,
                padding: "6px 12px", cursor: "pointer", fontSize: 13,
              }}
            >
              {r === "5" ? "5 min" : r === "15" ? "15 min" : "1h"}
            </button>
          ))}
        </div>

        <select
          value={timeRange}
          onChange={(e) => {
            const r = e.target.value as typeof timeRange;
            setTimeRange(r);
            requestAnimationFrame(() => applyTimeRange(r));
          }}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 10px", fontSize: 13, cursor: "pointer" }}
        >
          <option value="1d">Dzisiaj</option>
          <option value="2d">2 dni</option>
          <option value="5d">5 dni</option>
          <option value="all">Wszystko</option>
        </select>

        <button
          onClick={handleSync}
          disabled={syncing || loading}
          style={{ background: "#0f766e", color: "#e2e8f0", border: "none", borderRadius: 6, padding: "6px 14px", cursor: "pointer", fontSize: 13 }}
        >
          {syncing ? "Sync..." : "↓ Pobierz dane"}
        </button>

        <button
          onClick={() => loadData(selectedId, resolution)}
          disabled={loading}
          style={{ background: "#1e293b", color: "#94a3b8", border: "1px solid #334155", borderRadius: 6, padding: "6px 14px", cursor: "pointer", fontSize: 13 }}
        >
          {loading ? "Ładuję..." : "Odśwież"}
        </button>

        {lastRefresh && (
          <span style={{ color: "#64748b", fontSize: 12 }}>
            {lastRefresh.toLocaleTimeString("pl-PL")}
            <span style={{ marginLeft: 6, color: autoRefreshCountdown <= 15 ? "#f59e0b" : "#475569" }}>
              (auto {autoRefreshCountdown}s)
            </span>
          </span>
        )}

      </div>

      {error && (
        <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid #ef4444", borderRadius: 8, padding: "8px 14px", marginBottom: 12, color: "#fca5a5", fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Stats bar */}
      {latestCandle && (
        <div style={{ display: "flex", gap: 20, marginBottom: 12, flexWrap: "wrap" }}>
          {[
            { label: "Close", value: fmtPrice(latestCandle.close, asset?.currency ?? "USD") },
            { label: "RSI", value: latestCandle.rsi != null ? latestCandle.rsi.toFixed(1) : "—", color: latestCandle.rsi != null ? (latestCandle.rsi < 32 ? "#22c55e" : latestCandle.rsi > 68 ? "#ef4444" : "#e2e8f0") : undefined },
            { label: "VWAP", value: latestCandle.vwap != null ? fmtPrice(latestCandle.vwap, asset?.currency ?? "USD") : "—", color: latestCandle.vwap != null ? (latestCandle.close > latestCandle.vwap ? "#22c55e" : "#ef4444") : undefined },
            { label: "EMA9", value: latestCandle.ema9 != null ? latestCandle.ema9.toFixed(2) : "—" },
            { label: "EMA20", value: latestCandle.ema20 != null ? latestCandle.ema20.toFixed(2) : "—" },
            { label: "Vol ratio", value: latestCandle.volume_ratio != null ? `${latestCandle.volume_ratio.toFixed(1)}x` : "—", color: latestCandle.volume_ratio != null && latestCandle.volume_ratio >= 1.8 ? "#f59e0b" : undefined },
            { label: "Świece", value: `${candles.length}` },
            {
              label: "RS vs QQQ",
              value: rsData?.current_rs != null ? `${rsData.current_rs > 0 ? "+" : ""}${rsData.current_rs.toFixed(2)}%` : "—",
              color: rsData?.current_rs != null ? (rsData.current_rs >= 0 ? "#22c55e" : "#ef4444") : undefined,
            },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ color: "#64748b", fontSize: 11, marginBottom: 2 }}>{label}</div>
              <div style={{ color: color ?? "#e2e8f0", fontWeight: 600, fontSize: 14 }}>{value}</div>
            </div>
          ))}
          {orActive && (
            <div style={{ textAlign: "center", borderLeft: "1px solid #334155", paddingLeft: 20 }}>
              <div style={{ color: "#64748b", fontSize: 11, marginBottom: 2 }}>OR {or!.range_pct}%</div>
              <div style={{
                fontWeight: 700, fontSize: 13,
                color: or!.breakout_up ? "#22c55e" : or!.breakout_down ? "#ef4444" : "#fb923c",
              }}>
                {or!.breakout_up ? "▲ WYBICIE" : or!.breakout_down ? "▼ WYBICIE" : "W ZAKRESIE"}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Charts */}
      <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", overflow: "hidden", marginBottom: 16 }}>
        <div style={{ padding: "6px 14px", borderBottom: "1px solid #1e293b", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 13, marginRight: 4 }}>{asset?.symbol}</span>
          <span style={{ color: "#334155", fontSize: 10, marginRight: 4 }}>CET/CEST</span>
          {(["ema9","ema20","bb","vwap","or","poc","va","sr"] as (keyof Indicators)[]).map(id => (
            <IndToggle key={id} id={id} ind={ind} setInd={setInd} />
          ))}
          <button
            onClick={() => {
              const allOn = (Object.keys(ind) as (keyof Indicators)[]).every(k => ind[k]);
              setInd(Object.fromEntries(Object.keys(ind).map(k => [k, !allOn])) as unknown as Indicators);
            }}
            style={{ background: "transparent", border: "1px solid #334155", color: "#64748b", borderRadius: 4, padding: "2px 8px", fontSize: 11, cursor: "pointer", marginLeft: 4, userSelect: "none" }}
          >
            {(Object.keys(ind) as (keyof Indicators)[]).every(k => ind[k]) ? "Wyłącz wszystkie" : "Włącz wszystkie"}
          </button>
        </div>
        <div style={{ position: "relative" }}>
          <div ref={chartContainerRef} style={{ width: "100%" }} />
          <canvas
            ref={vpvrCanvasRef}
            style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
          />
        </div>
        <div style={{ borderTop: "1px solid #1e293b", padding: "4px 14px" }}>
          <span style={{ color: "#a78bfa", fontSize: 11 }}>RSI(14)</span>
        </div>
        <div ref={rsiContainerRef} style={{ width: "100%" }} />
        <div style={{ borderTop: "1px solid #1e293b", padding: "4px 14px" }}>
          <span style={{ color: "#64748b", fontSize: 11 }}>Wolumen</span>
        </div>
        <div ref={volumeContainerRef} style={{ width: "100%" }} />
        <div style={{ borderTop: "1px solid #1e293b", padding: "4px 14px", display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ color: "#94a3b8", fontSize: 11 }}>RS vs QQQ</span>
          {rsData?.current_rs != null && (
            <span style={{
              fontSize: 11, fontWeight: 700,
              color: rsData.current_rs >= 0 ? "#22c55e" : "#ef4444",
            }}>
              {rsData.current_rs > 0 ? "+" : ""}{rsData.current_rs.toFixed(2)}%
              {rsData.current_rs >= 0 ? " ▲ silniejszy niż QQQ" : " ▼ słabszy niż QQQ"}
            </span>
          )}
        </div>
        <div ref={rsContainerRef} style={{ width: "100%" }} />
      </div>

      {/* Signals + Patterns + S/R */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
        {/* Signals */}
        <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", padding: 16 }}>
          <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
            Sygnały intraday
            {signals && (
              <span style={{ color: "#64748b", fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
                ({signals.candles_count} świec)
              </span>
            )}
          </div>
          <BuySellBanner signals={signals} currency={asset?.currency ?? "USD"} />
          {signals?.regime && (
            <div style={{ marginBottom: 8 }}>
              <RegimeBadge regime={signals.regime} />
            </div>
          )}
          <div style={{ marginBottom: 8 }}>
            <AnomalyBadge
              data={anomaly}
              refreshing={anomalyRefreshing}
              onRefresh={async () => {
                setAnomalyRefreshing(true);
                try { setAnomaly(await api.anomalyRefresh(selectedId)); } catch { /* brak danych */ }
                finally { setAnomalyRefreshing(false); }
              }}
            />
          </div>
          <div style={{ marginBottom: 8 }}>
            <PEADBadge data={pead} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <InsiderBadge
              data={insider}
              currency={asset?.currency ?? "USD"}
              syncing={insiderSyncing}
              onSync={async () => {
                setInsiderSyncing(true);
                try {
                  await api.syncInsider(selectedId);
                  setInsider(await api.insiderSentiment(selectedId).catch(() => null));
                } catch { /* brak danych */ }
                finally { setInsiderSyncing(false); }
              }}
            />
          </div>
          {signals && signals.signals.length > 0 ? (
            signals.signals.map((s, i) => <SignalBadge key={i} signal={s} currency={asset?.currency ?? "USD"} />)
          ) : (
            <div style={{ color: "#475569", fontSize: 13 }}>
              {candles.length < 30 ? "Za mało danych — pobierz świece" : "Brak aktywnych sygnałów"}
            </div>
          )}
        </div>

        {/* Candlestick Patterns */}
        <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", padding: 16 }}>
          <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
            Formacje świecowe
            {signals?.patterns && signals.patterns.length > 0 && (
              <span style={{ color: "#64748b", fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
                ({signals.patterns.length})
              </span>
            )}
          </div>
          {signals?.patterns && signals.patterns.length > 0 ? (
            signals.patterns.map((p, i) => <PatternBadge key={i} p={p} />)
          ) : (
            <div style={{ color: "#475569", fontSize: 13 }}>
              {candles.length < 30 ? "Za mało danych" : "Brak wykrytych formacji"}
            </div>
          )}
        </div>

        {/* Backtest & Calibration */}
        <BacktestPanel
          backtest={backtest}
          running={backtestRunning}
          onRun={async () => {
            if (!selectedId) return;
            setBacktestRunning(true);
            try { setBacktest(await api.intradayBacktestRun(selectedId, resolution)); }
            catch (e) { setError(e instanceof Error ? e.message : "Błąd backtestingu"); }
            finally { setBacktestRunning(false); }
          }}
        />

        {/* AI Analysis */}
        <AIAnalysisPanel
          analysis={aiAnalysis}
          running={aiAnalysisRunning}
          onRun={async () => {
            if (!selectedId) return;
            setAiAnalysisRunning(true);
            try {
              const result = await api.intradayAIAnalysis(selectedId, resolution);
              aiAnalysisMapRef.current.set(selectedId, result);
              setAiAnalysis(result);
            }
            catch (e) { setError(e instanceof Error ? e.message : "Błąd analizy AI"); }
            finally { setAiAnalysisRunning(false); }
          }}
        />

        {/* S/R + OR */}
        <div style={{ background: "#0f172a", borderRadius: 10, border: "1px solid #1e293b", padding: 16 }}>
          <div style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 14, marginBottom: 12 }}>Poziomy cenowe</div>
          {signals ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {orActive && (
                <div style={{ marginBottom: 6, padding: "6px 8px", background: "rgba(251,146,60,0.08)", borderRadius: 6, border: "1px solid rgba(251,146,60,0.3)" }}>
                  <div style={{ color: "#fb923c", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>OPENING RANGE</div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span style={{ color: "#22c55e" }}>ORH: ${or!.high.toFixed(2)}</span>
                    <span style={{ color: "#ef4444" }}>ORL: ${or!.low.toFixed(2)}</span>
                    <span style={{ color: "#94a3b8" }}>{or!.range_pct}%</span>
                  </div>
                </div>
              )}
              {[...signals.resistance].reverse().map((r, i) => (
                <div key={`r${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: "#ef4444", fontSize: 12, fontWeight: 600 }}>R</span>
                  <span style={{ color: "#e2e8f0", fontSize: 13 }}>${r.toFixed(2)}</span>
                  {latestCandle && <span style={{ color: "#64748b", fontSize: 11 }}>{((r - latestCandle.close) / latestCandle.close * 100).toFixed(1)}%</span>}
                </div>
              ))}
              {latestCandle && (
                <div style={{ borderTop: "1px solid #1e293b", borderBottom: "1px solid #1e293b", padding: "4px 0", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#94a3b8", fontSize: 11 }}>CENA</span>
                  <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 13 }}>${latestCandle.close.toFixed(2)}</span>
                  {signals.current_vwap && (
                    <span style={{ color: latestCandle.close > signals.current_vwap ? "#22c55e" : "#ef4444", fontSize: 11 }}>
                      VWAP ${signals.current_vwap.toFixed(2)}
                    </span>
                  )}
                </div>
              )}
              {signals.support.map((s, i) => (
                <div key={`s${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: "#22c55e", fontSize: 12, fontWeight: 600 }}>S</span>
                  <span style={{ color: "#e2e8f0", fontSize: 13 }}>${s.toFixed(2)}</span>
                  {latestCandle && <span style={{ color: "#64748b", fontSize: 11 }}>{((s - latestCandle.close) / latestCandle.close * 100).toFixed(1)}%</span>}
                </div>
              ))}
              {signals.support.length === 0 && signals.resistance.length === 0 && !orActive && (
                <div style={{ color: "#475569", fontSize: 13 }}>Za mało danych do wykrycia poziomów</div>
              )}
            </div>
          ) : (
            <div style={{ color: "#475569", fontSize: 13 }}>Brak danych</div>
          )}
        </div>
      </div>
    </div>
  );
}