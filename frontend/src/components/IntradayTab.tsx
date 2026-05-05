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
import type { Asset, IntradayCandle, IntradaySignalsResponse, SwingSignal, OpeningRange, VolumeProfile, CandlePattern, RelativeStrengthData, MarketRegime } from "../lib/types";

function PatternBadge({ p }: { p: CandlePattern }) {
  const color = p.type === "bullish" ? "#22c55e" : p.type === "bearish" ? "#ef4444" : "#f59e0b";
  const bg = p.type === "bullish" ? "rgba(34,197,94,0.08)" : p.type === "bearish" ? "rgba(239,68,68,0.08)" : "rgba(245,158,11,0.08)";
  const icon = p.type === "bullish" ? "▲" : p.type === "bearish" ? "▼" : "◆";
  const time = new Date(p.timestamp).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
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

function toTimestamp(iso: string): Time {
  return (new Date(iso).getTime() / 1000) as Time;
}

function SignalBadge({ signal }: { signal: SwingSignal }) {
  const isBuy = signal.type === "BUY";
  const color = isBuy ? "#22c55e" : "#ef4444";
  const bg = isBuy ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)";
  const time = new Date(signal.timestamp).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
  return (
    <div style={{ background: bg, border: `1px solid ${color}`, borderRadius: 8, padding: "10px 14px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ color, fontWeight: 700, fontSize: 13 }}>{signal.type}</span>
        <span style={{ color: "#94a3b8", fontSize: 12 }}>{time}</span>
        <span style={{ color: "#e2e8f0", fontSize: 13, marginLeft: "auto" }}>${signal.price.toFixed(2)}</span>
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

interface Props {
  assets: Asset[];
}

export function IntradayTab({ assets }: Props) {
  const stocks = assets.filter((a) => a.type === "stock");

  const [selectedId, setSelectedId] = useState<string>(stocks[0]?.id ?? "");
  const [resolution, setResolution] = useState<Resolution>("15");
  const [candles, setCandles] = useState<IntradayCandle[]>([]);
  const [signals, setSignals] = useState<IntradaySignalsResponse | null>(null);
  const [rsData, setRsData] = useState<RelativeStrengthData | null>(null);
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
  const priceLineRefs = useRef<IPriceLine[]>([]);
  const vpDataRef = useRef<VolumeProfile | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

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

      if (bin.is_poc) {
        ctx.fillStyle = "rgba(251,191,36,0.85)";
      } else if (bin.in_va) {
        ctx.fillStyle = "rgba(99,102,241,0.45)";
      } else {
        ctx.fillStyle = "rgba(100,116,139,0.25)";
      }
      ctx.fillRect(x, yCenter - halfH, barW, halfH * 2);
    }
    ctx.resetTransform();
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

    const rsiChart = createChart(rsiContainerRef.current, {
      ...DARK_CHART_OPTIONS,
      height: 100,
      width: rsiContainerRef.current.clientWidth,
    });
    rsiChartRef.current = rsiChart;
    rsiSeriesRef.current = rsiChart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });

    const volChart = createChart(volumeContainerRef.current, {
      ...DARK_CHART_OPTIONS,
      height: 80,
      width: volumeContainerRef.current.clientWidth,
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

    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) {
        rsiChart.timeScale().setVisibleLogicalRange(range);
        volChart.timeScale().setVisibleLogicalRange(range);
        rsChart.timeScale().setVisibleLogicalRange(range);
      }
      drawVPVR();
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

  const loadData = useCallback(async (assetId: string, res: Resolution) => {
    if (!assetId) return;
    setLoading(true);
    setError(null);
    try {
      const [c, s, vpResult, rs] = await Promise.all([
        api.intradayCandles(assetId, res, 200),
        api.intradaySignals(assetId, res),
        api.intradayVolumeProfile(assetId, res, 300).catch(() => null),
        api.intradayRelativeStrength(assetId, res).catch(() => null),
      ]);
      setCandles(c);
      setSignals(s);
      setRsData(rs);
      vpDataRef.current = vpResult;
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

        chartRef.current?.timeScale().fitContent();
        rsiChartRef.current?.timeScale().fitContent();
        volumeChartRef.current?.timeScale().fitContent();

        // S/R price lines
        if (candleSeriesRef.current) {
          priceLineRefs.current.forEach((pl) => candleSeriesRef.current!.removePriceLine(pl));
          priceLineRefs.current = [];
          s?.support.forEach((level) => {
            const pl = candleSeriesRef.current!.createPriceLine({ price: level, color: "#22c55e", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `S ${level.toFixed(2)}` });
            priceLineRefs.current.push(pl);
          });
          s?.resistance.forEach((level) => {
            const pl = candleSeriesRef.current!.createPriceLine({ price: level, color: "#ef4444", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `R ${level.toFixed(2)}` });
            priceLineRefs.current.push(pl);
          });
          // Opening Range lines
          const or = s?.opening_range as OpeningRange | undefined;
          if (or?.high) {
            const plOrH = candleSeriesRef.current!.createPriceLine({ price: or.high, color: "#fb923c", lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `ORH ${or.high.toFixed(2)}` });
            priceLineRefs.current.push(plOrH);
          }
          if (or?.low) {
            const plOrL = candleSeriesRef.current!.createPriceLine({ price: or.low, color: "#fb923c", lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: `ORL ${or.low.toFixed(2)}` });
            priceLineRefs.current.push(plOrL);
          }
          // POC / VAH / VAL lines
          if (vpResult?.poc) {
            const plPoc = candleSeriesRef.current!.createPriceLine({ price: vpResult.poc, color: "#fbbf24", lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `POC ${vpResult.poc.toFixed(2)}` });
            priceLineRefs.current.push(plPoc);
          }
          if (vpResult?.vah) {
            const plVah = candleSeriesRef.current!.createPriceLine({ price: vpResult.vah, color: "#a78bfa", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `VAH ${vpResult.vah.toFixed(2)}` });
            priceLineRefs.current.push(plVah);
          }
          if (vpResult?.val) {
            const plVal = candleSeriesRef.current!.createPriceLine({ price: vpResult.val, color: "#a78bfa", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `VAL ${vpResult.val.toFixed(2)}` });
            priceLineRefs.current.push(plVal);
          }
        }
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
          rsChartRef.current?.timeScale().fitContent();
        }
        // Rysuj VPVR po załadowaniu świec (po fitContent)
        requestAnimationFrame(() => drawVPVR());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd ładowania danych");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(selectedId, resolution);
  }, [selectedId, resolution, loadData]);

  // Auto-refresh co AUTO_REFRESH_SEC sekund
  useEffect(() => {
    const interval = setInterval(() => {
      setAutoRefreshCountdown((prev) => {
        if (prev <= 1) {
          loadData(selectedId, resolution);
          return AUTO_REFRESH_SEC;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [selectedId, resolution, loadData]);

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

  const asset = assets.find((a) => a.id === selectedId);
  const latestCandle = candles[candles.length - 1];
  const or = signals?.opening_range as OpeningRange | undefined;
  const orActive = or && or.high != null;

  return (
    <div style={{ padding: "0 16px 32px" }}>
      {/* Toolbar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 16 }}>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px", fontSize: 13 }}
        >
          {stocks.map((a) => (
            <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>
          ))}
        </select>

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
            { label: "Close", value: `$${latestCandle.close.toFixed(2)}` },
            { label: "RSI", value: latestCandle.rsi != null ? latestCandle.rsi.toFixed(1) : "—", color: latestCandle.rsi != null ? (latestCandle.rsi < 32 ? "#22c55e" : latestCandle.rsi > 68 ? "#ef4444" : "#e2e8f0") : undefined },
            { label: "VWAP", value: latestCandle.vwap != null ? `$${latestCandle.vwap.toFixed(2)}` : "—", color: latestCandle.vwap != null ? (latestCandle.close > latestCandle.vwap ? "#22c55e" : "#ef4444") : undefined },
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
        <div style={{ padding: "8px 14px", borderBottom: "1px solid #1e293b", display: "flex", gap: 16, alignItems: "center" }}>
          <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 13 }}>{asset?.symbol}</span>
          <span style={{ color: "#f59e0b", fontSize: 11 }}>EMA9</span>
          <span style={{ color: "#818cf8", fontSize: 11 }}>EMA20</span>
          <span style={{ color: "#475569", fontSize: 11 }}>BB</span>
          <span style={{ color: "#f472b6", fontSize: 11 }}>VWAP</span>
          <span style={{ color: "#fb923c", fontSize: 11 }}>OR</span>
          <span style={{ color: "#fbbf24", fontSize: 11 }}>POC</span>
          <span style={{ color: "#a78bfa", fontSize: 11 }}>VA</span>
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
          {signals?.regime && (
            <div style={{ marginBottom: 12 }}>
              <RegimeBadge regime={signals.regime} />
            </div>
          )}
          {signals && signals.signals.length > 0 ? (
            signals.signals.map((s, i) => <SignalBadge key={i} signal={s} />)
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