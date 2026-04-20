import { useEffect, useState } from "react";
import { RefreshCw, Wrench, Moon, Sun, Database, Cpu, Timer, Play } from "lucide-react";
import type { Asset, MLModelRun, MLStatus } from "../lib/types";

type Props = {
  apiBase: string;
  setApiBase: (v: string) => void;
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
};

type ProviderState = {
  key_configured: boolean;
  last_ok: string | null;
  last_error: string | null;
  errors_24h: number;
};
type ProvidersStatus = Record<"massive" | "twelvedata" | "rapidapi" | "alpaca" | "alphavantage" | "finnhub", ProviderState>;

type AssetSignal = "green" | "red" | "neutral";

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

function useAssetSignals(apiBase: string, assets: Asset[], syncCounter?: number): Map<string, AssetSignal> {
  const [signals, setSignals] = useState<Map<string, AssetSignal>>(new Map());

  async function fetchAll() {
    const entries = await Promise.all(
      assets.map(async (a) => {
        try {
          const r = await fetch(`${apiBase}/assets/${a.id}/recommendation`);
          if (!r.ok) return [a.id, "neutral"] as const;
          const d = await r.json();
          const rec   = d.recommendation      as string | null;
          const ml5   = d.ml_prediction       as string | null;
          const ml20  = d.ml_20d_prediction   as string | null;
          const f5d   = d.forecast_dir_5d     as string | null;
          const f20d  = d.forecast_dir_20d    as string | null;
          const allGreen =
            rec  === "KUP"  &&
            ml5  === "up"   &&
            (ml20 === null || ml20 === "up") &&
            f5d  === "up"   &&
            f20d === "up";
          const allRed =
            rec  === "SPRZEDAJ" &&
            ml5  === "down"     &&
            (ml20 === null || ml20 === "down") &&
            f5d  === "down"     &&
            f20d === "down";
          return [a.id, allGreen ? "green" : allRed ? "red" : "neutral"] as const;
        } catch {
          return [a.id, "neutral"] as const;
        }
      })
    );
    setSignals(new Map(entries));
  }

  useEffect(() => {
    if (assets.length === 0) return;
    fetchAll();
    const id = setInterval(fetchAll, 5 * 60_000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, assets]);

  useEffect(() => {
    if (!syncCounter) return;
    const id = setTimeout(fetchAll, 3000);
    return () => clearTimeout(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncCounter]);

  return signals;
}

// ── Formatters ───────────────────────────────────────────────────────────────

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

// ── Hero ─────────────────────────────────────────────────────────────────────

export function Hero({
  apiBase, setApiBase,
  assets, selectedAsset, setSelectedAsset,
  onRefresh, onRepair,
  loading, repairing,
  lastRefreshedAt, mlStatus, mlModels,
  onSync, syncing, syncCounter,
  displayCurrency, setDisplayCurrency, usdPlnRate,
}: Props) {
  const [dark, setDark] = useDarkMode();
  const dbActive      = useDbPulse(loading);
  const countdown     = useSchedulerCountdown(apiBase);
  const providers     = useProviderStatus(apiBase, syncCounter);
  const isSyncing     = useSyncStatus(apiBase, syncing);
  const signals       = useAssetSignals(apiBase, assets, syncCounter);

  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick(n => n + 1), 30_000); return () => clearInterval(id); }, []);

  const trainedModels = mlModels.filter(m => m.is_active);
  const mlMode = mlStatus?.ml_mode ?? "heuristic";

  return (
    <div className="sticky-bar">
      {/* Branding */}
      <span className="sticky-brand">MStock</span>

      {/* Asset selector */}
      <label className="sticky-field">
        <span className="sticky-label">Aktywo</span>
        <select className="sticky-select" value={selectedAsset} onChange={e => setSelectedAsset(e.target.value)}>
          {(() => {
            const foreign  = assets.filter(a => a.type === "stock" && a.currency !== "PLN");
            const polish   = assets.filter(a => a.type === "stock" && a.currency === "PLN");
            const commodities = assets.filter(a => a.type !== "stock");
            const opt = (a: typeof assets[0]) => {
              const sig = signals.get(a.id);
              const dot = sig === "green" ? "🟢 " : sig === "red" ? "🔴 " : "";
              return <option key={a.id} value={a.id}>{dot}{a.symbol} — {a.name}</option>;
            };
            return (
              <>
                {foreign.length > 0 && <optgroup label="── Spółki zagraniczne">{foreign.map(opt)}</optgroup>}
                {polish.length > 0 && <optgroup label="── Spółki polskie (GPW)">{polish.map(opt)}</optgroup>}
                {commodities.length > 0 && <optgroup label="── Surowce">{commodities.map(opt)}</optgroup>}
              </>
            );
          })()}
        </select>
      </label>

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

      {/* Backend URL */}
      <label className="sticky-field sticky-url">
        <span className="sticky-label">Backend</span>
        <input className="sticky-input" value={apiBase} onChange={e => setApiBase(e.target.value)} />
      </label>

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
      <div className="sticky-models" title={trainedModels.length ? `Aktywne modele: ${trainedModels.map(m => m.target_name).join(", ")}` : "Brak wytrenowanych modeli"}>
        <Cpu size={13} />
        <span className="sticky-ml-badge" style={{
          background: trainedModels.length ? "rgba(22,163,74,.15)" : "rgba(148,163,184,.15)",
          color: trainedModels.length ? "var(--ok)" : "var(--text-3)",
        }}>
          {mlMode === "ml" ? "ML" : "HEU"} · {trainedModels.length} mdl
        </span>
        {(mlStatus?.targets ?? []).map(t => (
          <span key={t.target_name} title={`${t.target_label}: ${t.is_trained ? "wytrenowany" : "brak modelu"}`}
            style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
              background: t.is_trained ? "var(--ok)" : "rgba(148,163,184,.4)" }} />
        ))}
      </div>

      <div className="sticky-sep" />

      {/* Provider status — po prawej */}
      <div className="sticky-providers" title="Status providerów danych">
        <ProviderDot name="massive"      label="MAS" state={providers?.massive} />
        <ProviderDot name="twelvedata"   label="12D" state={providers?.twelvedata} />
        <ProviderDot name="rapidapi"     label="RAP" state={providers?.rapidapi} />
        <ProviderDot name="alpaca"       label="ALP" state={providers?.alpaca} />
        <ProviderDot name="alphavantage" label="AV"  state={providers?.alphavantage} />
        <ProviderDot name="finnhub"      label="FH"  state={providers?.finnhub} />
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
