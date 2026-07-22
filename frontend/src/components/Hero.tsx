import { useEffect, useRef, useState } from "react";
import { RefreshCw, Wrench, Moon, Sun, Database, Cpu, Timer, Play, Search, ChevronDown } from "lucide-react";
import type { Asset, AssetRecommendation, MLModelRun, MLStatus } from "../lib/types";

type Props = {
  apiBase: string;
  assets: Asset[];
  selectedAsset: string;
  setSelectedAsset: (v: string) => void;
  onRefresh: () => void;
  onRepair: () => void;
  loading: boolean;
  repairing: boolean;
  lastRefreshedAt: Date | null;
  mlStatus: MLStatus | null;
  mlModels: MLModelRun[];
  onSync: () => void;
  syncing: boolean;
  syncCounter?: number;
  displayCurrency: "original" | "PLN";
  setDisplayCurrency: (v: "original" | "PLN") => void;
  usdPlnRate: number | null;
  recommendations: AssetRecommendation[];
};

type ProviderState = {
  key_configured: boolean;
  last_ok: string | null;
  last_error: string | null;
  errors_24h: number;
};
type ProvidersStatus = Record<"massive" | "twelvedata" | "rapidapi" | "alphavantage" | "finnhub", ProviderState>;

// ── Hooks ────────────────────────────────────────────────────────────────────

function useDarkMode() {
  const [dark, setDark] = useState(() => {
    try { const s = localStorage.getItem("mstock-dark"); if (s !== null) return s === "true"; } catch {}
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    try { localStorage.setItem("mstock-dark", String(dark)); } catch {}
  }, [dark]);
  return [dark, setDark] as const;
}

function useDbPulse(loading: boolean) {
  const [active, setActive] = useState(false);
  useEffect(() => {
    if (loading) { setActive(true); return; }
    const t = setTimeout(() => setActive(false), 1200);
    return () => clearTimeout(t);
  }, [loading]);
  return active;
}

function useSyncStatus(apiBase: string, syncing: boolean) {
  const [backendSyncing, setBackendSyncing] = useState(false);
  useEffect(() => {
    function poll() {
      fetch(`${apiBase}/admin/sync-status`)
        .then(r => r.json())
        .then(d => setBackendSyncing(!!d.running))
        .catch(() => {});
    }
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [apiBase]);
  return backendSyncing || syncing;
}

function useSchedulerCountdown(apiBase: string) {
  const [nextRun, setNextRun] = useState<Date | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  useEffect(() => {
    function fetchNext() {
      fetch(`${apiBase}/admin/scheduler-status`)
        .then(r => r.json())
        .then(d => {
          const job = (d?.jobs ?? []).find((j: { id: string }) => j.id === "full-pipeline");
          if (job?.next_run) setNextRun(new Date(job.next_run));
        }).catch(() => {});
    }
    fetchNext();
    const id = setInterval(fetchNext, 30_000);
    return () => clearInterval(id);
  }, [apiBase]);

  useEffect(() => {
    function calc() {
      if (!nextRun) { setSecondsLeft(null); return; }
      setSecondsLeft(Math.max(0, Math.round((nextRun.getTime() - Date.now()) / 1000)));
    }
    calc();
    const id = setInterval(calc, 1000);
    return () => clearInterval(id);
  }, [nextRun]);

  return secondsLeft;
}

function useProviderStatus(apiBase: string, syncCounter?: number) {
  const [status, setStatus] = useState<ProvidersStatus | null>(null);
  useEffect(() => {
    function fetch_status() {
      fetch(`${apiBase}/admin/provider-status`)
        .then(r => r.json())
        .then(d => setStatus(d))
        .catch(() => {});
    }
    fetch_status();
    const id = setInterval(fetch_status, 120_000); // co 2 min
    return () => clearInterval(id);
  }, [apiBase]);
  // Re-fetch natychmiast po sync
  useEffect(() => {
    if (syncCounter === undefined || syncCounter === 0) return;
    const id = setTimeout(() => {
      fetch(`${apiBase}/admin/provider-status`)
        .then(r => r.json())
        .then(d => setStatus(d))
        .catch(() => {});
    }, 1500); // 1.5s opóźnienie żeby log zdążył się zapisać
    return () => clearTimeout(id);
  }, [syncCounter, apiBase]);
  return status;
}

function useIntradaySignals(apiBase: string, assets: Asset[]) {
  const [intradayMap, setIntradayMap] = useState<Map<string, "BUY" | "SELL" | null>>(new Map());
  useEffect(() => {
    const stockIds = assets.filter(a => a.type === "stock").map(a => a.id);
    if (stockIds.length === 0) return;
    async function fetchAll() {
      const results = await Promise.all(
        stockIds.map(async id => {
          try {
            const r = await fetch(`${apiBase}/assets/${id}/intraday/signals?resolution=15`);
            if (!r.ok) return [id, null] as const;
            const d = await r.json();
            const sigs: Array<{ type: string; strength: number }> = d.signals ?? [];
            if (sigs.some(s => s.type === "BUY" && s.strength >= 0.6)) return [id, "BUY"] as const;
            if (sigs.some(s => s.type === "SELL" && s.strength >= 0.6)) return [id, "SELL"] as const;
            return [id, null] as const;
          } catch {
            return [id, null] as const;
          }
        })
      );
      setIntradayMap(new Map(results));
    }
    fetchAll();
    const id = setInterval(fetchAll, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [apiBase, assets]);
  return intradayMap;
}


// ── Formatters ───────────────────────────────────────────────────────────────

function useMarketCountdowns() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  function sessionInfo(tz: string, openH: number, openM: number, closeH: number, closeM: number) {
    const local = new Date(now.toLocaleString("en-US", { timeZone: tz }));
    const day = local.getDay(); // 0=Sun, 6=Sat
    const isWeekend = day === 0 || day === 6;
    const cur = local.getHours() * 3600 + local.getMinutes() * 60 + local.getSeconds();
    const open = openH * 3600 + openM * 60;
    const close = closeH * 3600 + closeM * 60;
    const isOpen = !isWeekend && cur >= open && cur < close;

    let secsToOpen: number | null = null;
    if (!isOpen) {
      if (!isWeekend && cur < open) {
        secsToOpen = open - cur;
      } else {
        // Po zamknięciu lub weekend — do otwarcia następnego dnia roboczego
        const daysToNext = day === 5 ? 3 : day === 6 ? 2 : 1;
        secsToOpen = daysToNext * 24 * 3600 - cur + open;
      }
    }

    return { isOpen, secsLeft: isOpen ? close - cur : null, secsToOpen };
  }

  return {
    gpw: sessionInfo("Europe/Warsaw",   9,  0, 17,  5),
    us:  sessionInfo("America/New_York", 9, 30, 16,  0),
  };
}

function formatSessionTime(secs: number | null): string {
  if (secs === null || secs <= 0) return "";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function SessionChip({ label, info }: { label: string; info: { isOpen: boolean; secsLeft: number | null; secsToOpen: number | null } }) {
  const title = info.isOpen
    ? `Sesja ${label} otwarta — za ${formatSessionTime(info.secsLeft)} zamknięcie`
    : `Sesja ${label} zamknięta — otwiera za ${formatSessionTime(info.secsToOpen)}`;
  return (
    <div title={title} style={{ display: "flex", alignItems: "center", gap: 3, cursor: "default" }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
        background: info.isOpen ? "var(--ok)" : "var(--text-3)",
        boxShadow: info.isOpen ? "0 0 0 2px var(--ok)33" : undefined,
      }} />
      <span style={{
        fontSize: 10, fontWeight: 500, whiteSpace: "nowrap",
        color: info.isOpen ? "var(--text-1)" : "var(--text-3)",
        fontVariantNumeric: "tabular-nums",
      }}>
        {label}{info.isOpen ? ` ${formatSessionTime(info.secsLeft)}` : info.secsToOpen ? ` za ${formatSessionTime(info.secsToOpen)}` : ""}
      </span>
    </div>
  );
}

function formatCountdown(s: number | null): string {
  if (s === null) return "—";
  if (s <= 0) return "za chwilę…";
  const m = Math.floor(s / 60), sec = s % 60;
  return m > 0 ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

function formatAge(date: Date | null): string {
  if (!date) return "—";
  const secs = Math.floor((Date.now() - date.getTime()) / 1000);
  if (secs < 60)   return `${secs}s temu`;
  if (secs < 3600) return `${Math.floor(secs / 60)}min temu`;
  return `${Math.floor(secs / 3600)}h temu`;
}

function ageHours(iso: string | null): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / 3600_000;
}

// ── Provider Dot ─────────────────────────────────────────────────────────────

function ProviderDot({ name, label, state }: { name: string; label: string; state: ProviderState | undefined }) {
  if (!state) return null;

  const okAge   = ageHours(state.last_ok);
  const errAge  = ageHours(state.last_error);

  // Ustal kolor:
  // szary   = brak klucza
  // zielony = klucz jest + ostatni sync OK < 48h
  // żółty   = klucz jest + OK ale >48h temu (stale) lub błędy ale był ok
  // czerwony = klucz jest + brak ok, same błędy albo > 7 dni bez ok
  let color: string;
  let tooltipLines: string[];

  if (!state.key_configured) {
    color = "var(--text-3)";
    tooltipLines = [`${label}: brak klucza API w .env`];
  } else if (okAge !== null && okAge < 48) {
    color = "var(--ok)";
    tooltipLines = [
      `${label}: ✓ działa`,
      `Ostatni sync: ${okAge < 1 ? `${Math.round(okAge * 60)} min temu` : `${Math.round(okAge)}h temu`}`,
      ...(state.errors_24h > 0 ? [`Błędy 24h: ${state.errors_24h}x`] : []),
    ];
  } else if (okAge !== null && okAge < 168) {
    color = "var(--warn)";
    tooltipLines = [
      `${label}: ⚠ dane przestarzałe (${Math.round(okAge)}h temu)`,
      ...(state.errors_24h > 0 ? [`Błędy 24h: ${state.errors_24h}x`] : []),
    ];
  } else if (state.last_ok === null && state.last_error === null) {
    // Klucz jest, ale nigdy nie było żadnego synca — oczekiwanie na pierwszy cykl
    color = "var(--warn)";
    tooltipLines = [
      `${label}: klucz skonfigurowany`,
      `Oczekiwanie na pierwszy sync (scheduler co 60 min)`,
      `Uruchom ręcznie: POST /admin/run-pipeline`,
    ];
  } else {
    color = "var(--bad)";
    tooltipLines = [
      `${label}: ✗ ${okAge === null ? "brak udanych synców" : "brak synca >7 dni"}`,
      ...(state.errors_24h > 0 ? [`Błędy 24h: ${state.errors_24h}x`] : []),
      ...(state.last_error ? [`Ostatni błąd: ${new Date(state.last_error).toLocaleString("pl-PL")}`] : []),
    ];
  }

  const isActive = color === "var(--ok)";

  return (
    <div
      title={tooltipLines.join("\n")}
      style={{ display: "flex", alignItems: "center", gap: "3px", cursor: "default" }}
    >
      <span
        style={{
          display: "inline-block",
          width: 7, height: 7,
          borderRadius: "50%",
          background: color,
          boxShadow: isActive ? `0 0 0 2px ${color}33` : undefined,
          flexShrink: 0,
        }}
      />
      <span style={{ fontSize: 10, fontWeight: 500, color: "var(--text-3)", letterSpacing: "0.03em" }}>
        {label}
      </span>
    </div>
  );
}

function assetSignal(
  recommendation: AssetRecommendation | undefined,
  intraday: "BUY" | "SELL" | null | undefined,
) {
  const state = recommendation?.recommendation === "KUP" ? "🟢"
    : recommendation?.recommendation === "SPRZEDAJ" ? "🔴"
    : recommendation?.meta_gate_applied ? "⛔"
    : recommendation ? "🟡" : "⚪";
  const direction = recommendation?.forecast_dir_5d ?? recommendation?.ml_prediction;
  const forecast = direction === "up" ? "↗" : direction === "down" ? "↘" : "→";
  const intradayIcon = intraday === "BUY" ? "▲" : intraday === "SELL" ? "▼" : "";
  return { state, forecast, intradayIcon };
}

function AssetPicker({
  assets, selectedAsset, setSelectedAsset, recommendations, intradaySignals,
}: {
  assets: Asset[];
  selectedAsset: string;
  setSelectedAsset: (value: string) => void;
  recommendations: AssetRecommendation[];
  intradaySignals: Map<string, "BUY" | "SELL" | null>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const recMap = new Map(recommendations.map(rec => [rec.asset_id, rec]));
  const selected = assets.find(asset => asset.id === selectedAsset);
  const selectedSignal = assetSignal(recMap.get(selectedAsset), intradaySignals.get(selectedAsset));

  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  const normalized = query.trim().toLocaleLowerCase("pl-PL");
  const filtered = assets.filter(asset => !normalized ||
    `${asset.symbol} ${asset.name}`.toLocaleLowerCase("pl-PL").includes(normalized));
  const groups = [
    ["ETF", filtered.filter(a => a.type === "stock" && a.sector?.startsWith("ETF"))],
    ["Spółki zagraniczne", filtered.filter(a => a.type === "stock" && a.currency !== "PLN" && !a.sector?.startsWith("ETF"))],
    ["Spółki polskie (GPW)", filtered.filter(a => a.type === "stock" && a.currency === "PLN" && !a.sector?.startsWith("ETF"))],
    ["Surowce", filtered.filter(a => a.type !== "stock")],
  ] as const;

  return (
    <div className="asset-picker" ref={root}>
      <button className="asset-picker-trigger" onClick={() => setOpen(value => !value)} aria-expanded={open}>
        <span>{selectedSignal.state}</span>
        <span className="asset-picker-forecast">{selectedSignal.forecast}{selectedSignal.intradayIcon}</span>
        <strong>{selected?.symbol ?? selectedAsset}</strong>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="asset-picker-panel">
          <div className="asset-picker-search">
            <Search size={15} />
            <input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Szukaj symbolu lub nazwy…" />
          </div>
          <div className="asset-picker-legend">🟢 kup · 🔴 sprzedaj · 🟡 neutralnie · ⛔ meta blokada · ↗/↘ prognoza 5d · ▲/▼ intraday</div>
          <div className="asset-picker-list">
            {groups.map(([label, rows]) => rows.length > 0 && (
              <div key={label}>
                <div className="asset-picker-group">{label}</div>
                {rows.map(asset => {
                  const rec = recMap.get(asset.id);
                  const signal = assetSignal(rec, intradaySignals.get(asset.id));
                  return (
                    <button key={asset.id} className={`asset-picker-row${asset.id === selectedAsset ? " selected" : ""}`}
                      onClick={() => { setSelectedAsset(asset.id); setOpen(false); setQuery(""); }}>
                      <span className="asset-picker-state">{signal.state}</span>
                      <span className="asset-picker-direction">{signal.forecast}{signal.intradayIcon}</span>
                      <span className="asset-picker-symbol">{asset.symbol}</span>
                      <span className="asset-picker-name">{asset.name}</span>
                      {rec?.meta_trade_probability != null && <span className="asset-picker-meta">meta {rec.meta_trade_probability.toFixed(0)}%</span>}
                    </button>
                  );
                })}
              </div>
            ))}
            {filtered.length === 0 && <div className="asset-picker-empty">Brak pasujących aktywów</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Hero ─────────────────────────────────────────────────────────────────────

export function Hero({
  apiBase,
  assets, selectedAsset, setSelectedAsset,
  onRefresh, onRepair,
  loading, repairing,
  lastRefreshedAt, mlStatus, mlModels,
  onSync, syncing, syncCounter,
  displayCurrency, setDisplayCurrency, usdPlnRate,
  recommendations,
}: Props) {
  const [dark, setDark] = useDarkMode();
  const dbActive         = useDbPulse(loading);
  const countdown        = useSchedulerCountdown(apiBase);
  const providers        = useProviderStatus(apiBase, syncCounter);
  const isSyncing        = useSyncStatus(apiBase, syncing);
  const marketCountdowns = useMarketCountdowns();
  const intradaySignals  = useIntradaySignals(apiBase, assets);

  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick(n => n + 1), 30_000); return () => clearInterval(id); }, []);

  const trainedModels = mlModels.filter(m => m.is_active);
  const mlMode = mlStatus?.ml_mode ?? "heuristic";
  const mlModeLabel = mlMode === "ml" ? "ML" : mlMode === "ml_partial" ? "MIX" : mlMode === "emergency_off" ? "OFF" : "HEU";

  return (
    <div className="sticky-bar">
      {/* Branding */}
      <span className="sticky-brand">MStock</span>

      {/* Asset selector */}
      <div className="sticky-field">
        <span className="sticky-label">Aktywo</span>
        <AssetPicker assets={assets} selectedAsset={selectedAsset} setSelectedAsset={setSelectedAsset}
          recommendations={recommendations} intradaySignals={intradaySignals} />
      </div>

      {/* Currency toggle */}
      <label className="sticky-field">
        <span className="sticky-label">Waluta</span>
        <div style={{ display: "flex", gap: "2px" }}>
          <button
            className="sticky-btn"
            style={{
              padding: "2px 8px", fontSize: "0.78rem", borderRadius: "5px 0 0 5px",
              background: displayCurrency === "original" ? "var(--accent)" : "var(--bg-subtle)",
              color: displayCurrency === "original" ? "#fff" : "var(--text-2)",
              border: "1px solid var(--border)", cursor: "pointer",
            }}
            onClick={() => setDisplayCurrency("original")}
          >Oryg.</button>
          <button
            className="sticky-btn"
            style={{
              padding: "2px 8px", fontSize: "0.78rem", borderRadius: "0 5px 5px 0",
              background: displayCurrency === "PLN" ? "var(--accent)" : "var(--bg-subtle)",
              color: displayCurrency === "PLN" ? "#fff" : "var(--text-2)",
              border: "1px solid var(--border)", borderLeft: "none", cursor: "pointer",
            }}
            onClick={() => setDisplayCurrency("PLN")}
          >PLN</button>
        </div>
      </label>
      {displayCurrency === "PLN" && (
        <span style={{ fontSize: "0.73rem", color: "var(--text-3)", whiteSpace: "nowrap" }}>
          {usdPlnRate != null ? `1 USD = ${usdPlnRate.toFixed(4)} PLN` : "kurs…"}
        </span>
      )}

      <div className="sticky-sep" />

      {/* DB indicator */}
      <div className="sticky-indicator" title="Aktywność bazy danych">
        <Database size={13} />
        <span className={`sticky-db-dot ${dbActive ? "db-active" : ""}`} />
      </div>

      {/* Last refresh age */}
      <div className="sticky-indicator sticky-age" title="Czas ostatniego odświeżenia UI">
        <RefreshCw size={12} style={{ opacity: 0.55 }} />
        <span>{formatAge(lastRefreshedAt)}</span>
      </div>

      {/* Countdown */}
      <div className="sticky-indicator" title="Czas do kolejnego automatycznego cyklu schedulera" style={{ minWidth: 68 }}>
        <Timer size={12} style={{ opacity: 0.55 }} />
        <span style={{
          fontVariantNumeric: "tabular-nums",
          color: countdown !== null && countdown <= 60 ? "var(--warn)" : "var(--text-3)",
          fontWeight: countdown !== null && countdown <= 60 ? 600 : 400,
        }}>
          {formatCountdown(countdown)}
        </span>
      </div>

      <div className="sticky-sep" />

      {/* ML models */}
      <div className="sticky-models" title={`Automatyczna aktywacja ML: live ${mlStatus?.eligible_models ?? 0}/${mlStatus?.active_models ?? 0}, shadow ${mlStatus?.shadow_models ?? 0}, degraded ${mlStatus?.degraded_models ?? 0}`}>
        <Cpu size={13} />
        <span className="sticky-ml-badge" style={{
          background: trainedModels.length ? "rgba(22,163,74,.15)" : "rgba(148,163,184,.15)",
          color: trainedModels.length ? "var(--ok)" : "var(--text-3)",
        }}>
          {mlModeLabel} · {mlStatus?.eligible_models ?? 0}/{mlStatus?.active_models ?? trainedModels.length}
        </span>
        {(mlStatus?.targets ?? []).map(t => (
          <span key={t.target_name} title={`${t.target_label}: ${t.activation_state}`}
            style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
              background: t.activation_state === "eligible" ? "var(--ok)" : t.activation_state === "degraded" ? "#dc2626" : t.is_trained ? "#d97706" : "rgba(148,163,184,.4)" }} />
        ))}
      </div>

      <div className="sticky-sep" />

      {/* Provider status */}
      <div className="sticky-providers" title="Status providerów danych">
        <ProviderDot name="massive"      label="MAS" state={providers?.massive} />
        <ProviderDot name="twelvedata"   label="12D" state={providers?.twelvedata} />
        <ProviderDot name="rapidapi"     label="RAP" state={providers?.rapidapi} />
        <ProviderDot name="alphavantage" label="AV"  state={providers?.alphavantage} />
        <ProviderDot name="finnhub"      label="FH"  state={providers?.finnhub} />
      </div>

      <div className="sticky-sep" />

      {/* Odliczanie do końca sesji */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <SessionChip label="GPW" info={marketCountdowns.gpw} />
        <SessionChip label="US"  info={marketCountdowns.us} />
      </div>

      {/* Spacer fills remaining space */}
      <div style={{ flex: 1 }} />

      {/* Dark mode toggle */}
      <button className="sticky-icon-btn" onClick={() => setDark(d => !d)}
        title={dark ? "Tryb jasny" : "Tryb ciemny"} aria-label="Przełącz motyw">
        {dark ? <Sun size={15} /> : <Moon size={15} />}
      </button>

      {/* Odśwież */}
      <button className={`sticky-btn sticky-btn-primary${loading ? " loading" : ""}`}
        onClick={onRefresh} disabled={loading}>
        <RefreshCw size={14} className={loading ? "spin" : ""} />
        {loading ? "Ładowanie…" : "Odśwież"}
      </button>

      {/* Sync ręczny */}
      <button
        className={`sticky-btn sticky-btn-secondary${isSyncing ? " loading" : ""}`}
        onClick={onSync}
        disabled={isSyncing}
        title={isSyncing ? "Sync trwa — poczekaj na zakończenie bieżącego cyklu" : "Uruchamia pełny cykl pipeline'u w tle (sync cen, newsów, ML, alerty)"}
      >
        <Play size={13} />
        {isSyncing ? "Sync…" : "Sync"}
      </button>

      {/* Napraw */}
      <button className={`sticky-btn sticky-btn-secondary${repairing ? " loading" : ""}`}
        onClick={onRepair} disabled={repairing}>
        <Wrench size={14} />
        {repairing ? "Naprawianie…" : "Napraw asset"}
      </button>
    </div>
  );
}
