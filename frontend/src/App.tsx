import React, { useEffect, useMemo, useState } from "react";
import {
  Bell,
  Brain,
  Gauge,
  ShieldAlert,
  FileText,
  Mail,
  MessageCircle,
  Rows3,
  Star,
  GitCompareArrows,
  ActivitySquare,
  WandSparkles,
  Trash2,
  X,
} from "lucide-react";
import { api, setApiBaseUrl } from "./lib/api";
import { formatPct, formatRatio, titleize } from "./lib/format";
import type {
  AlertItem,
  AssetDataQuality,
  PriceBar,
  EnsembleLeaderboard,
  EnsembleSignal,
  AssetRecommendation,
  Asset,
  DataQualityReport,
  AssetCreate,
  CompareAssetRow,
  Forecast,
  ForecastQualitySummary,
  MLDatasetStats,
  MLBacktest,
  MLModelRun,
  MLExplanation,
  MLActiveModel,
  MLPrediction,
  MLStatus,
  NarrativePoint,
  NotificationChannel,
  NotificationEvent,
  ReportResponse,
  StoredThesis,
  StrategyComparison,
  ThesisOutcome,
  ThesisQualityByHorizon,
  ThesisQualitySummary,
  WalkForwardBacktest,
  Watchlist,
  MLModelComparison,
} from "./lib/types";
import {
  OutcomesChart,
  PriceHistoryChart,
  ForecastHistoryChart,
  NarrativeHistoryChart,
  ThesisQualityChart,
} from "./components/Charts";
import { DataTable } from "./components/DataTable";
import { Hero } from "./components/Hero";
import { KpiCard } from "./components/KpiCard";
import { ColTip } from "./components/Tip";
import { PageContainer, Section } from "./components/Layout";
import { MetaRow, Panel, Pill } from "./components/Panel";

function humanizeError(message: string) {
  const lower = message.toLowerCase();
  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return "Frontend nie może połączyć się z backendem. Sprawdź, czy backend działa, czy URL API jest poprawny oraz czy CORS jest włączony.";
  }
  if (lower.includes("missing alphavantage_api_key")) {
    return "Brakuje klucza ALPHAVANTAGE_API_KEY w backend/.env.";
  }
  if (lower.includes("missing finnhub_api_key")) {
    return "Brakuje klucza FINNHUB_API_KEY w backend/.env.";
  }
  if (lower.includes("smtp not configured")) {
    return "SMTP nie jest skonfigurowany. Uzupełnij backend/.env.";
  }
  if (lower.includes("twilio whatsapp not configured")) {
    return "WhatsApp przez Twilio nie jest skonfigurowany. Uzupełnij backend/.env.";
  }
  return message;
}

const ML_TARGETS = [
  { value: "target_up_5d",          label: "Kierunek 5d",       description: "Czy cena wzrośnie w ciągu 5 dni?" },
  { value: "target_up_20d",         label: "Kierunek 20d",      description: "Czy cena wzrośnie w ciągu 20 dni?" },
  { value: "target_thesis_success", label: "Skuteczność tezy",  description: "Czy teza okazała się kierunkowo poprawna po 5 dniach?" },
] as const;

export default function App() {
  const [apiBase, setApiBase] = useState(api.apiBase);
  const updateApiBase = (url: string) => { setApiBase(url); setApiBaseUrl(url); };
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAsset, setSelectedAsset] = useState("nvda");
  const [loading, setLoading] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncCounter, setSyncCounter] = useState(0);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [mlWorking, setMlWorking] = useState<string | null>(null); // null = idle, string = opis operacji
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const [latestThesis, setLatestThesis] = useState<StoredThesis | null>(null);
  const [latestForecasts, setLatestForecasts] = useState<Forecast[]>([]);
  const [forecastHistory, setForecastHistory] = useState<Forecast[]>([]);
  const [thesisOutcomes, setThesisOutcomes] = useState<ThesisOutcome[]>([]);
  const [thesisQualitySummary, setThesisQualitySummary] =
    useState<ThesisQualitySummary | null>(null);
  const [thesisQualityByHorizon, setThesisQualityByHorizon] = useState<
    ThesisQualityByHorizon[]
  >([]);
  const [forecastQualitySummary, setForecastQualitySummary] = useState<
    ForecastQualitySummary[]
  >([]);
  const [narrativeHistory, setNarrativeHistory] = useState<NarrativePoint[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [compareRows, setCompareRows] = useState<CompareAssetRow[]>([]);
  const [compareAssetIds, setCompareAssetIds] = useState<string[]>([]);
  const [aggregateRows, setAggregateRows] = useState<any[]>([]);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [events, setEvents] = useState<NotificationEvent[]>([]);
  const [lastReport, setLastReport] = useState<ReportResponse | null>(null);

  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null);
  const [mlPrediction, setMlPrediction] = useState<MLPrediction | null>(null);
  const [mlModelsState, setMlModelsState] = useState<MLModelRun[]>([]);
  const [mlBacktestsState, setMlBacktestsState] = useState<MLBacktest[]>([]);
  const [mlDatasetStats, setMlDatasetStats] = useState<MLDatasetStats | null>(
    null
  );
  const [mlExplanation, setMlExplanation] = useState<MLExplanation | null>(null);
  const [mlComparison, setMlComparison] = useState<MLModelComparison[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [recommendations, setRecommendations] = useState<AssetRecommendation[]>([]);
  const [dataQuality, setDataQuality] = useState<DataQualityReport | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceBar[]>([]);
  const [ensembleSignal, setEnsembleSignal] = useState<EnsembleSignal | null>(null);
  const [ensembleLeaderboard, setEnsembleLeaderboard] = useState<EnsembleLeaderboard[]>([]);
  const [ensembleMode, setEnsembleMode] = useState<string>("ensemble_weighted");
  const [showAddAsset, setShowAddAsset] = useState(false);
  const [newAsset, setNewAsset] = useState<AssetCreate>({
    id: "", symbol: "", name: "", type: "stock",
    sector: "", price_symbol: "", news_symbol: "", news_term: "", metal_price_fn: "",
  });
  const [mlActiveTarget, setMlActiveTarget] = useState<string>("target_up_5d");
  const [cmpSort, setCmpSort] = useState<{ col: string; dir: 1 | -1 }>({ col: "asset_id", dir: 1 });
  const [strategyComparison, setStrategyComparison] =
    useState<StrategyComparison | null>(null);
  const [walkForwardResult, setWalkForwardResult] =
    useState<WalkForwardBacktest | null>(null);
  const [allComparisons, setAllComparisons] = useState<StrategyComparison[]>(
    []
  );

  const [displayCurrency, setDisplayCurrency] = useState<"original" | "PLN">("PLN");
  const [usdPlnRate, setUsdPlnRate] = useState<number | null>(null);

  useEffect(() => {
    // Próba 1: NBP API
    fetch("https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json")
      .then(r => r.json())
      .then(d => { const rate = d.rates?.[0]?.mid; if (rate) setUsdPlnRate(rate); })
      .catch(() => {
        // Próba 2: open.er-api.com (darmowy, bez klucza)
        fetch("https://open.er-api.com/v6/latest/USD")
          .then(r => r.json())
          .then(d => { const rate = d.rates?.PLN; if (rate) setUsdPlnRate(rate); })
          .catch(() => {});
      });
  }, []);

  useEffect(() => {
    api.assets()
      .then((rows) => {
        setAssets(rows);
        if (rows.length > 0 && !rows.some((x) => x.id === selectedAsset)) {
          setSelectedAsset(rows[0].id);
        }
      })
      .catch((err) => setError(humanizeError(String(err))));
  }, [selectedAsset]);

  const selectedMeta = useMemo(
    () => assets.find((asset) => asset.id === selectedAsset) ?? null,
    [assets, selectedAsset]
  );

  async function runSync() {
    if (syncing) return;
    setSyncing(true);
    setInfo("");
    setError("");
    try {
      const res = await fetch(`${apiBase}/admin/run-pipeline`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (res.status === 409) {
        setInfo("Sync już trwa — poczekaj na zakończenie bieżącego cyklu.");
      } else if (!res.ok) {
        setError(humanizeError(body?.detail || body?.message || `${res.status} ${res.statusText}`));
      } else {
        setInfo("Sync uruchomiony w tle. Przycisk odblokuje się automatycznie po zakończeniu.");
      }
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setSyncing(false);
      setSyncCounter(n => n + 1);
    }
  }

  async function refresh() {
    if (!selectedAsset) return;

    setLoading(true);
    setError("");
    setInfo("");

    try {
      const selectedIds = compareAssetIds.length > 0
        ? Array.from(new Set([...compareAssetIds, selectedAsset]))
        : Array.from(new Set([selectedAsset, "aapl", "gold", "nvda", "silver"]));

      const [
        thesis,
        forecasts,
        forecastHist,
        outcomes,
        thesisSummary,
        thesisByHorizon,
        forecastSummary,
        narratives,
        assetAlerts,
        wl,
        aggregate,
        compare,
        notificationChannels,
        notificationEvents,
        currentMlStatus,
        currentMlPrediction,
        currentMlExplanation,
        currentMlModels,
        currentMlBacktests,
        currentMlDatasetStats,
        currentMlComparison,
        currentAvailableModels,
        currentStrategyComparison,
        currentAllComparisons,
        currentRecommendations,
        currentDataQuality,
        currentPriceHistory,
        currentEnsembleSignal,
        currentEnsembleLeaderboard,
      ] = await Promise.all([
        api.latestThesis(selectedAsset).catch(() => null),
        api.latestForecasts(selectedAsset).catch(() => []),
        api.forecastHistory(selectedAsset).catch(() => []),
        api.thesisOutcomes(selectedAsset).catch(() => []),
        api.thesisQualitySummary(selectedAsset).catch(() => null),
        api.thesisQualityByHorizon(selectedAsset).catch(() => []),
        api.forecastQualitySummary(selectedAsset).catch(() => []),
        api.narrativeHistory(selectedAsset, 14).catch(() => []),
        api.assetAlerts(selectedAsset).catch(() => []),
        api.watchlists().catch(() => []),
        api.aggregateDashboard(selectedIds).catch(() => ({
          asset_ids: selectedIds,
          rows: [],
        })),
        api.compareAssets(selectedIds).catch(() => ({
          asset_ids: selectedIds,
          rows: [],
        })),
        api.notificationChannels().catch(() => []),
        api.notificationEvents().catch(() => []),
        api.mlStatus().catch(() => null),
        api.latestMlPrediction(selectedAsset, mlActiveTarget).catch(() => null),
        api.mlExplain(selectedAsset, mlActiveTarget).catch(() => null),
        api.mlModels().catch(() => []),
        api.mlBacktests().catch(() => []),
        api.mlDatasetStats().catch(() => null),
        Promise.all([
          api.mlComparison("target_up_5d").catch(() => []),
          api.mlComparison("target_up_20d").catch(() => []),
        ]).then(([a, b]) => [...a, ...b]),
        api.mlAvailableModels().catch(() => ({ available: [] })),
        api.latestHeuristicVsMl(selectedAsset).catch(() => null),
        api.allHeuristicVsMl().catch(() => []),
        api.recommendations().catch(() => []),
        api.dataQuality().catch(() => null),
        api.priceHistory(selectedAsset, 5000).catch(() => []),
        api.ensembleSignal(selectedAsset, ensembleMode).catch(() => null),
        api.ensembleLeaderboard().catch(() => []),
      ]);

      setLatestThesis(thesis);
      setLatestForecasts(forecasts);
      setForecastHistory(forecastHist);
      setThesisOutcomes(outcomes);
      setThesisQualitySummary(thesisSummary);
      setThesisQualityByHorizon(thesisByHorizon);
      setForecastQualitySummary(forecastSummary);
      setNarrativeHistory(narratives);
      setAlerts(assetAlerts);
      setWatchlists(wl);
      setAggregateRows(aggregate.rows ?? []);
      setCompareRows(compare.rows ?? []);
      setChannels(notificationChannels);
      setEvents(notificationEvents);

      setMlStatus(currentMlStatus);
      setMlPrediction(currentMlPrediction);
      setMlModelsState(currentMlModels);
      setMlBacktestsState(currentMlBacktests);
      setMlDatasetStats(currentMlDatasetStats);
      setMlComparison(currentMlComparison);
      setAvailableModels(currentAvailableModels?.available ?? []);
      setStrategyComparison(currentStrategyComparison);
      setAllComparisons(currentAllComparisons);
      setLastRefreshedAt(new Date());
      setRecommendations(currentRecommendations);
      setDataQuality(currentDataQuality);
      setPriceHistory(currentPriceHistory);
      setEnsembleSignal(currentEnsembleSignal);
      setEnsembleLeaderboard(currentEnsembleLeaderboard);
      setMlExplanation(currentMlExplanation);
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setLoading(false);
    }
  }

  async function bootstrapSelectedAsset() {
    if (!selectedAsset) return;

    setBootstrapping(true);
    setError("");
    setInfo("");

    try {
      const result = await api.bootstrapAsset(selectedAsset);
      const errors = Array.isArray((result as any).errors)
        ? (result as any).errors
        : [];

      setInfo(
        errors.length
          ? `Bootstrap zakończony częściowo: ${errors.join(" | ")}`
          : `Bootstrap ukończony dla ${selectedAsset}.`
      );

      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setBootstrapping(false);
    }
  }

  async function toggleMlMode() {
    try {
      const next = !(mlStatus?.ml_enabled ?? false);
      const result = await api.setMlMode(next);
      setInfo(`Tryb przełączony na: ${result.ml_mode === "ml" ? "ML" : "Heurystyka"}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function addAssetNow() {
    try {
      if (!newAsset.id || !newAsset.symbol || !newAsset.name) {
        setError("Wymagane: id, symbol, name.");
        return;
      }
      const payload: AssetCreate = {
        ...newAsset,
        id: newAsset.id.toLowerCase().trim(),
        symbol: newAsset.symbol.toUpperCase().trim(),
        price_symbol:   newAsset.price_symbol   || undefined,
        news_symbol:    newAsset.news_symbol    || undefined,
        news_term:      newAsset.news_term      || undefined,
        metal_price_fn: newAsset.metal_price_fn || undefined,
      };
      await api.createAsset(payload);
      setInfo(`Dodano aktywo: ${payload.name} (${payload.id}).`);
      setShowAddAsset(false);
      setNewAsset({ id: "", symbol: "", name: "", type: "stock", sector: "", price_symbol: "", news_symbol: "", news_term: "", metal_price_fn: "" });
      const rows = await api.assets();
      setAssets(rows);
      setSelectedAsset(payload.id);
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function deleteAssetNow(assetId: string) {
    if (!confirm(`Usunąć aktywo "${assetId}" wraz ze wszystkimi danymi?`)) return;
    try {
      await api.deleteAsset(assetId);
      setInfo(`Usunięto: ${assetId}.`);
      const rows = await api.assets();
      setAssets(rows);
      if (selectedAsset === assetId && rows.length > 0) setSelectedAsset(rows[0].id);
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function buildMlDatasetNow() {
    setMlWorking("Budowanie datasetu…");
    try {
      const result = await api.buildMlDataset();
      setInfo(`Dataset zbudowany: ${result.built_rows} nowych wierszy, łącznie ${result.total_rows}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setMlWorking(null);
    }
  }

  async function trainMlNow() {
    const label = ML_TARGETS.find(t => t.value === mlActiveTarget)?.label ?? mlActiveTarget;
    const models = availableModels.length > 0 ? availableModels : ["logistic_regression"];
    const modelAbbrs = models.map(m => ({ logistic_regression: "LR", random_forest: "RF", xgboost: "XGB", lstm: "LSTM" }[m] ?? m)).join(", ");
    setMlWorking(`Trening ${modelAbbrs} — ${label}…`);
    try {
      for (const modelName of models) {
        await api.trainMlModel(mlActiveTarget, modelName, selectedAsset);
      }
      setInfo(`Wytrenowano modele (${modelAbbrs}) dla ${selectedAsset} / ${label}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setMlWorking(null);
    }
  }

  async function trainAllMlNow() {
    const modelList = availableModels.map(m => ({ logistic_regression:"LR", random_forest:"RF", xgboost:"XGB", lstm:"LSTM" }[m] ?? m)).join(", ");
    setMlWorking(`Trening wszystkich modeli (${modelList}) — może potrwać kilka minut…`);
    try {
      const results = await api.trainAllMlModels();
      const trained = results.filter((r: any) => !r.skipped).length;
      const skipped = results.filter((r: any) => r.skipped).length;
      setInfo(`Trening zakończony: ${trained} wytrenowanych, ${skipped} pominiętych (za mało danych).`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setMlWorking(null);
    }
  }

  async function runMlBacktestNow() {
    try {
      const result = await api.runMlBacktest(mlActiveTarget, selectedAsset);
      setInfo(`Backtest zapisany dla ${selectedAsset}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function runWalkForwardNow() {
    try {
      const result = await api.walkForwardBacktest(mlActiveTarget, selectedAsset);
      setWalkForwardResult(result);
      setInfo("Backtest walk-forward zakończony.");
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function compareModesNow() {
    try {
      const result = await api.compareHeuristicVsMl(selectedAsset);
      setStrategyComparison(result);
      setInfo(`Porównanie heurystyka vs ML gotowe dla ${selectedAsset}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function rescoreMlNow() {
    try {
      await api.scoreAssetMl(selectedAsset, mlActiveTarget);
      setInfo(`Przeliczono predykcję ML dla ${selectedAsset}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function createReport() {
    try {
      const report = await api.createAssetReport(selectedAsset);
      setLastReport(report);
      setInfo(`Wygenerowano raport PDF: ${report.file_name}`);
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function notifyFirstEmail() {
    try {
      const emailChannel = channels.find((x) => x.channel_type === "email");
      if (!emailChannel) {
        setError("Brak kanału email. Dodaj go w sekcji Notifications.");
        return;
      }
      await api.sendEmailNotification(
        emailChannel.id,
        `Daily summary for ${selectedAsset}`,
        `Thesis update for ${selectedAsset}`,
        selectedAsset
      );
      setInfo("Wysłano email.");
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function notifyFirstWhatsApp() {
    try {
      const waChannel = channels.find((x) => x.channel_type === "whatsapp");
      if (!waChannel) {
        setError("Brak kanału WhatsApp. Dodaj go w sekcji Notifications.");
        return;
      }
      await api.sendWhatsAppNotification(
        waChannel.id,
        `Alert update for ${selectedAsset}`,
        selectedAsset
      );
      setInfo("Wysłano WhatsApp.");
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function createDefaultWatchlist() {
    try {
      await api.createWatchlist(
        "Main watchlist",
        "Default personal watchlist",
        true
      );
      setInfo("Utworzono watchlistę.");
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function addSelectedToFirstWatchlist() {
    try {
      if (watchlists.length === 0) {
        await createDefaultWatchlist();
      }
      const latest = await api.watchlists();
      const first = latest[0];
      if (!first) return;
      await api.addAssetToWatchlist(first.id, selectedAsset);
      setInfo(`Dodano ${selectedAsset} do watchlisty ${first.name}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  async function createEmailChannelDemo() {
    try {
      await api.createNotificationChannel(
        "email",
        "demo@example.com",
        "Demo email",
        true
      );
      setInfo("Dodano demo kanał email.");
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    }
  }

  useEffect(() => {
    refresh();
  }, [selectedAsset]);

  // Re-fetch predykcji i XAI gdy user zmieni aktywny cel ML
  useEffect(() => {
    if (!selectedAsset) return;
    setMlExplanation(null);
    setMlPrediction(null);
    Promise.all([
      api.latestMlPrediction(selectedAsset, mlActiveTarget).catch(() => null),
      api.mlExplain(selectedAsset, mlActiveTarget).catch(() => null),
    ]).then(([pred, expl]) => {
      setMlPrediction(pred);
      setMlExplanation(expl);
    });
  }, [mlActiveTarget]);

  // Auto-refresh UI gdy scheduler zakończy cykl.
  // Odpytuje /admin/scheduler-status co 15s i porównuje next_run.
  // Gdy next_run zmieni się na późniejszą datę → scheduler właśnie zakończył cykl → odśwież.
  useEffect(() => {
    let prevNextRun: string | null = null;
    let firstCall = true;

    const id = setInterval(async () => {
      try {
        const r = await fetch(`${apiBase}/admin/scheduler-status`);
        const d = await r.json();
        const jobs = d?.jobs ?? [];
        const job = jobs.find((j: { id: string }) => j.id === "full-pipeline");
        const nextRun: string | null = job?.next_run ?? null;

        if (firstCall) {
          prevNextRun = nextRun;
          firstCall = false;
          return;
        }

        // next_run przeskoczył do przodu → scheduler właśnie uruchomił cykl
        if (nextRun && prevNextRun && nextRun !== prevNextRun) {
          prevNextRun = nextRun;
          refresh();
        }
      } catch {
        // cicho ignoruj błędy sieciowe
      }
    }, 15_000);

    return () => clearInterval(id);
  }, [apiBase, selectedAsset]);


  // ── Sortowanie tabel ────────────────────────────────────────────────────────
  const [sortStates, setSortStates] = useState<Record<string, { key: string; dir: "asc" | "desc" }>>({});

  function sortedRows<T extends Record<string, unknown>>(tableId: string, rows: T[], defaultKey = ""): T[] {
    const s = sortStates[tableId];
    if (!s?.key) return rows;
    return [...rows].sort((a, b) => {
      const av = a[s.key]; const bv = b[s.key];
      const numA = parseFloat(String(av)); const numB = parseFloat(String(bv));
      const isNum = !isNaN(numA) && !isNaN(numB);
      let cmp = isNum ? numA - numB : String(av ?? "").localeCompare(String(bv ?? ""), "pl");
      return s.dir === "asc" ? cmp : -cmp;
    });
  }

  function SortTh({ tableId, colKey, label, tip, side = "top", style }:
    { tableId: string; colKey: string; label: string; tip?: string; side?: "top"|"bottom"|"left"|"right"; style?: React.CSSProperties }) {
    const s = sortStates[tableId];
    const active = s?.key === colKey;
    return (
      <th
        style={{ ...style, cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
        onClick={() => setSortStates(prev => ({
          ...prev,
          [tableId]: { key: colKey, dir: active && prev[tableId]?.dir === "asc" ? "desc" : "asc" }
        }))}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
          {label}
          {tip && <ColTip label="" text={tip} side={side} style={{ marginLeft: 0 }} />}
          <span style={{ opacity: active ? 1 : 0.25, fontSize: "0.65rem" }}>
            {active && s.dir === "asc" ? "▲" : "▼"}
          </span>
        </span>
      </th>
    );
  }

  // ── Pomocniki konwersji walutowej ───────────────────────────────────────────
  const assetCurrencyMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of assets) m.set(a.id, a.currency ?? "USD");
    return m;
  }, [assets]);

  function convertPrice(price: number | null, origCurrency = "USD"): number | null {
    if (price == null) return null;
    // Jeśli cena jest już w PLN — nie przeliczaj
    if (origCurrency === "PLN") return price;
    // Jeśli chcemy PLN i cena jest w USD — przelicz
    if (displayCurrency === "PLN" && origCurrency.startsWith("USD") && usdPlnRate != null)
      return price * usdPlnRate;
    return price;
  }

  function displayLabel(origCurrency: string): string {
    if (origCurrency === "PLN") return "PLN";
    return displayCurrency === "PLN" && origCurrency.startsWith("USD") ? "PLN" : origCurrency;
  }

  function fmtPrice(price: number | null, origCurrency = "USD"): string {
    const v = convertPrice(price, origCurrency);
    if (v == null) return "—";
    return v.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  const selectedOrigCurrency = selectedMeta?.currency ?? "USD";

  const displayPriceHistory = useMemo(() => {
    // Jeśli aktywo jest już w PLN — nie przeliczaj
    if (selectedOrigCurrency === "PLN") return priceHistory;
    // Jeśli chcemy PLN i mamy kurs — przelicz
    if (displayCurrency === "PLN" && usdPlnRate)
      return priceHistory.map(b => ({ ...b, close: b.close * usdPlnRate }));
    return priceHistory;
  }, [priceHistory, displayCurrency, usdPlnRate, selectedOrigCurrency]);

  return (
    <PageContainer>
      <Hero
        apiBase={apiBase}
        setApiBase={updateApiBase}
        assets={assets}
        selectedAsset={selectedAsset}
        setSelectedAsset={setSelectedAsset}
        onRefresh={refresh}
        onRepair={bootstrapSelectedAsset}
        loading={loading}
        repairing={bootstrapping}
        onSync={runSync}
        syncing={syncing}
        syncCounter={syncCounter}
        lastRefreshedAt={lastRefreshedAt}
        mlStatus={mlStatus}
        mlModels={mlModelsState}
        displayCurrency={displayCurrency}
        setDisplayCurrency={setDisplayCurrency}
        usdPlnRate={usdPlnRate}
      />

      {/* Rząd 1 — akcje ML */}
      {mlWorking && (
        <div style={{
          display: "flex", alignItems: "center", gap: "0.6rem",
          padding: "0.45rem 0.8rem", marginBottom: "0.5rem",
          borderRadius: "8px", background: "var(--bg-subtle)",
          border: "1px solid var(--border)", fontSize: "0.82rem", color: "var(--text-2)",
        }}>
          <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid var(--accent)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite", flexShrink: 0 }} />
          {mlWorking}
        </div>
      )}
      <div className="toolbar-row">
        <button className="secondary-button" onClick={toggleMlMode}>
          <WandSparkles size={16} />
          {mlStatus?.ml_enabled ? "Przełącz na heurystykę" : "Przełącz na ML"}
        </button>
        <button className="secondary-button" onClick={buildMlDatasetNow} disabled={!!mlWorking}>
          <Rows3 size={16} />
          {mlWorking?.startsWith("Budowanie") ? "Budowanie…" : "Zbuduj dataset ML"}
        </button>
        <button className="secondary-button" onClick={trainMlNow} disabled={!!mlWorking}>
          <Brain size={16} />
          {mlWorking?.startsWith("Trening ") && !mlWorking?.startsWith("Trening wszystkich") ? "Trenuję…" : `Trenuj modele — ${ML_TARGETS.find(t => t.value === mlActiveTarget)?.label ?? mlActiveTarget}`}
        </button>
        <button className="secondary-button" onClick={trainAllMlNow} disabled={!!mlWorking}>
          <Brain size={16} />
          {mlWorking?.startsWith("Trening wszystkich") ? "Trenuję…" : `Trenuj wszystkie modele (${availableModels.map(m => ({ logistic_regression:"LR", random_forest:"RF", xgboost:"XGB", lstm:"LSTM" }[m] ?? m)).join(", ") || "—"})`}
        </button>
        <button className="secondary-button" onClick={runMlBacktestNow}>
          <GitCompareArrows size={16} />
          Backtest ML
        </button>
        <button className="secondary-button" onClick={runWalkForwardNow}>
          <GitCompareArrows size={16} />
          Walk-forward
        </button>
        <button className="secondary-button" onClick={compareModesNow}>
          <Rows3 size={16} />
          Porównaj heurystyka vs ML
        </button>
        <button className="secondary-button" onClick={rescoreMlNow}>
          <ActivitySquare size={16} />
          Przelicz predykcję ML
        </button>
      </div>

      {/* Rząd 2 — pozostałe akcje */}
      <div className="toolbar-row" style={{ marginTop: "0.4rem" }}>
        <button className="secondary-button" onClick={createReport}>
          <FileText size={16} />
          Eksport PDF
        </button>
        <button className="secondary-button" onClick={addSelectedToFirstWatchlist}>
          <Star size={16} />
          Dodaj do watchlisty
        </button>
        <button className="secondary-button" onClick={notifyFirstEmail}>
          <Mail size={16} />
          Wyślij email
        </button>
        <button className="secondary-button" onClick={notifyFirstWhatsApp}>
          <MessageCircle size={16} />
          Wyślij WhatsApp
        </button>
      </div>

      {info ? <div className="info-box">{info}</div> : null}
      {error ? <div className="error-box">{error}</div> : null}

      <div className="kpi-grid">
        <KpiCard
          tooltip="Symbol i nazwa wybranego aktywa. Wybierz aktywo w górnym pasku."
          title="Aktywo"
          value={selectedMeta?.symbol ?? "—"}
          hint={selectedMeta?.name ?? ""}
          icon={<Brain size={18} />}
        />
        <KpiCard
          tooltip="Syntetyczna pewność bieżącej tezy inwestycyjnej (0–100%). Wynika z conviction score, siły trendu i spójności sygnałów. >70% = silna teza."
          title="Pewność tezy"
          value={
            latestThesis ? formatPct(latestThesis.thesis_confidence) : "—"
          }
          hint={titleize(latestThesis?.regime)}
          icon={<Gauge size={18} />}
        />
        <KpiCard
          tooltip="Historyczny % trafnych prognoz kierunku ceny dla tego aktywa. Liczone z zamkniętych tez z outcomes. Wartość >55% jest statystycznie istotna."
          title="Trafność kierunkowa"
          value={
            thesisQualitySummary
              ? formatRatio(thesisQualitySummary.directional_accuracy)
              : "—"
          }
          hint={`Outcomes: ${thesisQualitySummary?.total_outcomes ?? 0}`}
          icon={<ShieldAlert size={18} />}
        />
        <KpiCard
          tooltip="Liczba aktywnych alertów dla wybranego aktywa. Alerty generowane automatycznie po wykryciu: wysokiej kruchości, zmiany narracji, degradacji prognozy."
          title="Alerty"
          value={String(alerts.length)}
          hint="dla wybranego aktywa"
          icon={<Bell size={18} />}
        />
      </div>

      {/* ── Historia ceny ── */}
      {selectedMeta && (
        <div style={{ marginBottom: "24px" }}>

          {/* ── Pasek sygnałów ── */}
          {(() => {
            const rec    = recommendations.find(r => r.asset_id === selectedAsset) ?? null;
            const recKey = rec?.recommendation === "KUP" ? "buy" : rec?.recommendation === "SPRZEDAJ" ? "sell" : "hold";
            const mlDir  = mlPrediction?.predicted_label?.toLowerCase() ?? null;
            const mlKey  = mlDir === "up" ? "buy" : mlDir === "down" ? "sell" : "hold";
            const ensAct = ensembleSignal?.action ?? null;
            const ensKey = ensAct === "KUP" ? "buy" : ensAct === "SPRZEDAJ" ? "sell" : "hold";

            const colors: Record<string, { bg: string; border: string; text: string }> = {
              buy:  { bg: "rgba(22,163,74,0.11)",  border: "rgba(22,163,74,0.38)",  text: "#16a34a" },
              sell: { bg: "rgba(220,38,38,0.10)",  border: "rgba(220,38,38,0.38)",  text: "#dc2626" },
              hold: { bg: "var(--bg-card)",         border: "var(--border)",          text: "var(--text-2)" },
            };

            const mlLabel   = mlActiveTarget === "target_up_5d" ? "5d" : mlActiveTarget === "target_up_20d" ? "20d" : "teza";
            const mlVerdict = mlDir === "up" ? "WZROST" : mlDir === "down" ? "SPADEK" : "—";

            function SignalBox({ colorKey, title, verdict, detail, tooltip }: {
              colorKey: string; title: string; verdict: string; detail: string; tooltip: string;
            }) {
              const c = colors[colorKey] ?? colors.hold;
              return (
                <div title={tooltip} style={{
                  flex: "1 1 0", borderRadius: "8px", padding: "9px 14px",
                  background: c.bg, border: `1.5px solid ${c.border}`,
                  cursor: "default", minWidth: 0,
                }}>
                  <div style={{ fontSize: "0.63rem", fontWeight: 600, letterSpacing: "0.09em",
                    textTransform: "uppercase", color: "var(--text-3)", marginBottom: "3px" }}>
                    {title}
                  </div>
                  <div style={{ fontSize: "1.25rem", fontWeight: 700, lineHeight: 1, color: c.text }}>
                    {verdict}
                  </div>
                  <div style={{ fontSize: "0.70rem", marginTop: "5px", color: "var(--text-2)" }}>
                    {detail}
                  </div>
                </div>
              );
            }

            return (
              <div style={{ display: "flex", gap: "10px", marginBottom: "10px" }}>
                <SignalBox
                  colorKey={recKey}
                  title="Rekomendacja"
                  verdict={rec?.recommendation ?? "—"}
                  detail={rec ? `score ${rec.composite_score} · pewność: ${rec.confidence_label}` : "brak danych"}
                  tooltip={rec?.rationale ?? "Brak danych rekomendacji"}
                />
                <SignalBox
                  colorKey={mlKey}
                  title={`ML · ${mlLabel}`}
                  verdict={mlVerdict}
                  detail={mlPrediction ? `p(wzrost) = ${(mlPrediction.probability_up * 100).toFixed(1)}%` : "brak predykcji"}
                  tooltip={mlPrediction ? `Cel: ${mlPrediction.target_name} | p(up) = ${(mlPrediction.probability_up * 100).toFixed(1)}%` : "Brak predykcji ML — wytrenuj modele"}
                />
                <SignalBox
                  colorKey={ensKey}
                  title="Ensemble ważony"
                  verdict={ensAct ?? "—"}
                  detail={ensembleSignal
                    ? `p=${ensembleSignal.final_probability_up.toFixed(1)}% · konsensus: ${ensembleSignal.consensus}`
                    : "brak danych"}
                  tooltip={ensembleSignal?.rationale ?? "Brak sygnału ensemble"}
                />
              </div>
            );
          })()}

          {displayCurrency === "PLN" && selectedOrigCurrency !== "PLN" && usdPlnRate == null && (
            <div style={{ fontSize: "0.75rem", color: "var(--warn, #b45309)", marginBottom: "4px", paddingLeft: "4px" }}>
              Brak kursu USD/PLN — wykres w oryginalnej walucie. Sprawdź połączenie z internetem.
            </div>
          )}
          <PriceHistoryChart bars={displayPriceHistory} symbol={selectedMeta.symbol} currency={displayLabel(selectedOrigCurrency)} />
        </div>
      )}

      <Section
        title="Fundament ML"
        subtitle="Trzy targety: kierunek 5d, kierunek 20d, skuteczność tezy."
      >
        {/* ── Selektor targetu ── */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.82rem", color: "var(--text-2)", fontWeight: 500 }}>Aktywny cel:</span>
          {ML_TARGETS.map((t) => (
            <button
              key={t.value}
              onClick={() => setMlActiveTarget(t.value)}
              title={t.description}
              style={{
                padding: "0.3rem 0.7rem",
                borderRadius: "6px",
                border: mlActiveTarget === t.value ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                background: mlActiveTarget === t.value ? "var(--bg-hover)" : "var(--bg-card)",
                color: "var(--text)",
                fontWeight: mlActiveTarget === t.value ? 600 : 400,
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              {t.label}
              {mlStatus?.targets?.find(x => x.target_name === t.value)?.is_trained && (
                <span style={{ marginLeft: "0.35rem", color: "#16a34a", fontSize: "0.7rem" }}>✓</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Karty statusu per target ── */}
        <div style={{ display: "flex", gap: "0.6rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          {(mlStatus?.targets ?? []).map((t) => (
            <div key={t.target_name} style={{
              flex: "1 1 200px",
              padding: "0.6rem 0.8rem",
              borderRadius: "8px",
              border: `1.5px solid ${t.is_trained ? "rgba(22,163,74,0.4)" : "var(--border)"}`,
              background: t.is_trained ? "rgba(22,163,74,0.05)" : "var(--bg-card)",
            }}>
              <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>{t.target_label}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-2)" }}>
                {t.is_trained
                  ? <span style={{ color: "#16a34a" }}>✓ Wytrenowany — {t.model_name}</span>
                  : <span style={{ color: "var(--text-3)" }}>Brak modelu</span>}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-2)", marginTop: "0.15rem" }}>
                {t.dataset_rows} oznaczonych wierszy
              </div>
            </div>
          ))}
        </div>

        {/* ── Stan ML — kompaktowy pasek info ── */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: "1.2rem", alignItems: "center",
          padding: "0.55rem 0.9rem", borderRadius: "8px", marginBottom: "1rem",
          background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: "0.8rem",
        }}>
          <span title="Aktywny tryb: ml lub heuristic">
            <span style={{ color: "var(--text-2)" }}>tryb </span>
            <strong style={{ color: mlStatus?.ml_enabled ? "#16a34a" : "var(--text)" }}>{mlStatus?.ml_mode ?? "—"}</strong>
          </span>
          <span title="Łączna liczba wierszy w datasecie treningowym">
            <span style={{ color: "var(--text-2)" }}>wierszy </span>
            <strong>{mlStatus?.dataset_rows ?? 0}</strong>
            <span style={{ color: "var(--text-3)" }}> / min {mlStatus?.min_training_rows ?? 0}</span>
          </span>
          <span title="Oznaczone wiersze per horyzont (ile rekordów ma uzupełniony target)">
            <span style={{ color: "var(--text-2)" }}>oznaczone </span>
            <span title="target_up_1d">1d: <strong>{mlDatasetStats?.labeled_rows_1d ?? 0}</strong></span>
            {" · "}
            <span title="target_up_5d">5d: <strong>{mlDatasetStats?.labeled_rows_5d ?? 0}</strong></span>
            {" · "}
            <span title="target_up_20d">20d: <strong>{mlDatasetStats?.labeled_rows_20d ?? 0}</strong></span>
            {" · "}
            <span title="target_thesis_success">teza: <strong>{mlDatasetStats?.thesis_success_rows ?? 0}</strong></span>
          </span>
          {availableModels.length > 0 && (
            <span title="Typy modeli dostępne do treningu (zainstalowane pakiety)">
              <span style={{ color: "var(--text-2)" }}>dostępne modele </span>
              <strong>{availableModels.map(m => ({ logistic_regression:"LR", random_forest:"RF", xgboost:"XGB", lstm:"LSTM" }[m] ?? m)).join(", ")}</strong>
            </span>
          )}
          <span title={mlStatus?.ready_for_training ? "Wystarczająco danych do treningu" : "Zbyt mało danych — zbieraj przez scheduler"}>
            {mlStatus?.ready_for_training
              ? <span style={{ color: "#16a34a" }}>✓ gotowy do treningu</span>
              : <span style={{ color: "var(--text-3)" }}>· zbieranie danych…</span>}
          </span>
        </div>

        <div className="grid-2">
          {/* ── Panel: predykcja + wyjaśnienie ── */}
          <Panel title={`Predykcja ML — ${ML_TARGETS.find(t => t.value === mlActiveTarget)?.label ?? mlActiveTarget}`}>
            {mlExplanation ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {/* Verdict */}
                <div style={{
                  display: "flex", alignItems: "center", gap: "0.75rem",
                  padding: "0.6rem 0.8rem", borderRadius: "8px",
                  background: mlExplanation.predicted_label === "up" ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)",
                  border: `1.5px solid ${mlExplanation.predicted_label === "up" ? "#16a34a" : "#dc2626"}`,
                }}>
                  <span style={{ fontSize: "1.5rem", fontWeight: 700, color: mlExplanation.predicted_label === "up" ? "#16a34a" : "#dc2626" }}>
                    {mlExplanation.predicted_label === "up" ? "▲" : "▼"}
                  </span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem", color: mlExplanation.predicted_label === "up" ? "#16a34a" : "#dc2626" }}>
                      {mlExplanation.predicted_label === "up" ? "BULLISH" : "BEARISH"}{" — "}{(mlExplanation.probability_up * 100).toFixed(1)}% p(up)
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-2)", marginTop: "0.2rem" }}>
                      {mlExplanation.interpretation}
                    </div>
                  </div>
                </div>

                {/* Wkłady */}
                <div>
                  <div style={{ fontSize: "0.72rem", fontWeight: 500, color: "var(--text-2)", marginBottom: "0.3rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Wkład cech</div>
                  {mlExplanation.prediction_contributions.slice(0, 8).map((c) => {
                    const maxAbs = Math.max(...mlExplanation.prediction_contributions.map(x => Math.abs(x.contribution)));
                    const pct = maxAbs > 0 ? Math.abs(c.contribution) / maxAbs : 0;
                    const isBull = c.contribution > 0;
                    const col = isBull ? "#16a34a" : "#dc2626";
                    return (
                      <div key={c.feature} style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.2rem" }}>
                        <span style={{ width: "140px", fontSize: "0.74rem", color: "var(--text-2)", flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.feature.replace(/_/g, " ")}</span>
                        <div style={{ flex: 1, height: "9px", background: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                          <div style={{ width: `${(pct * 100).toFixed(1)}%`, height: "100%", background: col, borderRadius: "3px" }} />
                        </div>
                        <span style={{ width: "50px", fontSize: "0.71rem", textAlign: "right", color: col, fontWeight: 500 }}>{isBull ? "+" : ""}{c.contribution.toFixed(3)}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Top importances */}
                <div>
                  <div style={{ fontSize: "0.72rem", fontWeight: 500, color: "var(--text-2)", marginBottom: "0.3rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Najważniejsze cechy (globalne)</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                    {mlExplanation.feature_importances.slice(0, 5).map((f, i) => (
                      <span key={f.feature} style={{
                        padding: "0.18rem 0.45rem", borderRadius: "5px", fontSize: "0.72rem",
                        fontWeight: i < 2 ? 600 : 400,
                        background: f.direction === "bullish" ? "rgba(22,163,74,0.1)" : "rgba(220,38,38,0.1)",
                        color: f.direction === "bullish" ? "#15803d" : "#b91c1c",
                        border: `1px solid ${f.direction === "bullish" ? "rgba(22,163,74,0.25)" : "rgba(220,38,38,0.25)"}`,
                      }}>
                        {i + 1}. {f.feature.replace(/_/g, " ")} ({f.importance.toFixed(3)})
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : mlPrediction ? (() => {
              const label = mlPrediction.predicted_label;
              const probUp = mlPrediction.probability_up;
              const isUp = label === "up";
              const col = isUp ? "#16a34a" : "#dc2626";
              const bg = isUp ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)";
              let modelsUsed: string[] = [];
              try {
                const raw = JSON.parse(mlPrediction.raw_json ?? "{}");
                modelsUsed = raw.models_used ?? [];
              } catch { /* ignore */ }
              return (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.8rem", borderRadius: "8px", background: bg, border: `1.5px solid ${col}` }}>
                    <span style={{ fontSize: "1.5rem", fontWeight: 700, color: col }}>{isUp ? "▲" : "▼"}</span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem", color: col }}>
                        {isUp ? "BULLISH" : "BEARISH"}{" — "}{(probUp * 100).toFixed(1)}% p(up)
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-2)", marginTop: "0.2rem" }}>
                        {new Date(mlPrediction.snapshot_at).toLocaleString("pl-PL")}
                        {modelsUsed.length > 0 && ` · modele: ${modelsUsed.join(", ")}`}
                      </div>
                    </div>
                  </div>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-3)", margin: 0 }}>
                    Brak szczegółowego wyjaśnienia — wytrenuj model LR aby zobaczyć wkłady cech.
                  </p>
                </div>
              );
            })() : (
              <p className="long-text">Brak predykcji. Wytrenuj model i kliknij &ldquo;Przelicz predykcję ML&rdquo;.</p>
            )}
          </Panel>

          {/* ── Panel: model registry ── */}
          <Panel title="Rejestr modeli">
            <DataTable
              maxRows={12}
              columns={["Cel","Model","Wierszy","Aktywny","Wytrenowano"]}
              rows={mlModelsState.map((row) => ({
                "Cel": row.target_name,
                "Model": row.model_name,
                "Wierszy": String(row.dataset_rows),
                "Aktywny": row.is_active ? "✓" : "—",
                "Wytrenowano": new Date(row.trained_at).toLocaleDateString("pl-PL"),
              }))}
            />
          </Panel>

        </div>

        {/* ── Panel: porównanie modeli (pełna szerokość, modele jako kolumny) ── */}
        <div style={{ marginTop: "1rem" }}>
        {(() => {
          const MODEL_SHORT: Record<string, string> = {
            logistic_regression: "LR", random_forest: "RF", xgboost: "XGB", lstm: "LSTM",
          };
          const MODEL_LONG: Record<string, string> = {
            logistic_regression: "Logistic Regression — szybki model liniowy, interpretowalny",
            random_forest: "Random Forest — 300 drzew decyzyjnych, odporny na szum",
            xgboost: "XGBoost — gradient boosting, najlepszy dla danych tabelarycznych",
            lstm: "LSTM (PyTorch) — sieć rekurencyjna, wymaga >60 sekwencji (~4 lata danych dziennych)",
          };
          const filtered = mlComparison.filter(r => r.target_name === mlActiveTarget);
          const modelTypes = [...new Set(filtered.map(r => r.model_name))].sort();
          // pivot: asset → { model → metrics }
          const byAsset: Record<string, Record<string, typeof filtered[0]>> = {};
          for (const r of filtered) {
            if (!byAsset[r.asset_id]) byAsset[r.asset_id] = {};
            byAsset[r.asset_id][r.model_name] = r;
          }
          type PRow = { asset_id: string; maxRows: number; [k: string]: number | string | boolean };
          const pivotRows: PRow[] = Object.entries(byAsset).map(([assetId, models]) => {
            const row: PRow = { asset_id: assetId, maxRows: 0 };
            for (const mn of modelTypes) {
              const m = models[mn];
              const s = MODEL_SHORT[mn] ?? mn;
              row[`${s}_acc`] = m ? m.accuracy : -1;
              row[`${s}_f1`]  = m ? m.f1       : -1;
              row[`${s}_global`] = m ? (m.is_global ?? false) : false;
              if (m && m.train_rows > (row.maxRows as number)) row.maxRows = m.train_rows;
            }
            return row;
          });

          const sortFn = (a: PRow, b: PRow): number => {
            const av = a[cmpSort.col], bv = b[cmpSort.col];
            if (typeof av === "string") return cmpSort.dir * av.localeCompare(bv as string);
            return cmpSort.dir * ((bv as number) - (av as number));
          };
          const sorted = [...pivotRows].sort(sortFn);

          const thClick = (col: string) =>
            setCmpSort(prev => ({ col, dir: prev.col === col ? (-prev.dir as 1 | -1) : -1 }));
          const sortArrow = (col: string) =>
            cmpSort.col === col ? (cmpSort.dir === -1 ? " ▼" : " ▲") : "";

          const thStyle: React.CSSProperties = {
            cursor: "pointer", userSelect: "none",
            padding: "0.35rem 0.5rem", fontSize: "0.74rem",
            fontWeight: 600, color: "var(--text-2)", textAlign: "right" as const,
            whiteSpace: "nowrap", borderBottom: "1px solid var(--border)",
            background: "var(--bg-card)",
          };
          const tdStyle = (val: number): React.CSSProperties => ({
            padding: "0.3rem 0.5rem", fontSize: "0.78rem", textAlign: "right",
            color: val < 0 ? "var(--text-3)" : val >= 0.55 ? "#16a34a" : val >= 0.5 ? "var(--text)" : "#dc2626",
            fontWeight: val >= 0.55 ? 600 : 400,
          });

          const colGroups: { col: string; label: string; tooltip: string }[] = [];
          for (const mn of modelTypes) {
            const s = MODEL_SHORT[mn] ?? mn;
            const long = MODEL_LONG[mn] ?? mn;
            colGroups.push({ col: `${s}_acc`, label: `${s} Acc`, tooltip: `${long}\n\nAccuracy = (TP+TN)/(wszystkie). Jak często model ma rację.` });
            colGroups.push({ col: `${s}_f1`,  label: `${s} F1`,  tooltip: `${long}\n\nF1 = 2·Prec·Recall/(Prec+Recall). Lepszy od Accuracy przy niezbalansowanych klasach.` });
          }

          return (
            <Panel title="Porównanie modeli">
              {filtered.length === 0 ? (
                <p className="long-text">Brak wytrenowanych modeli. Kliknij „Trenuj wszystkie modele" po zebraniu danych.</p>
              ) : (
                <div style={{ maxHeight: "22rem", overflowY: "auto", overflowX: "auto" }}>
                  {mlComparison.some(r => r.is_global) && (
                    <div style={{ fontSize: "0.72rem", color: "var(--text-3)", marginBottom: "0.3rem" }}>
                      * model globalny (wytrenowany na wszystkich aktywach łącznie, brak modelu per-aktywo)
                    </div>
                  )}
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={{ ...thStyle, textAlign: "left" }} onClick={() => thClick("asset_id")}
                          title="Symbol aktywa — kliknij aby sortować">
                          Aktywo{sortArrow("asset_id")}
                        </th>
                        {colGroups.map(({ col, label, tooltip }) => (
                          <th key={col} style={thStyle} onClick={() => thClick(col)} title={tooltip}>
                            {label}{sortArrow(col)}
                          </th>
                        ))}
                        <th style={thStyle} onClick={() => thClick("maxRows")}
                          title="Liczba wierszy treningowych (80% datasetu)">
                          Wierszy{sortArrow("maxRows")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map(row => (
                        <tr key={row.asset_id} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem", fontWeight: 600 }}>
                            {(row.asset_id as string).toUpperCase()}
                          </td>
                          {colGroups.map(({ col }) => {
                            const v = row[col] as number;
                            const modelShort = col.replace(/_acc$|_f1$/, "");
                            const isGlobal = row[`${modelShort}_global`] as boolean;
                            return (
                              <td key={col} style={{ ...tdStyle(v), opacity: isGlobal ? 0.65 : 1 }}
                                title={isGlobal ? "Model globalny (nie per-aktywo)" : undefined}>
                                {v < 0 ? "—" : `${(v * 100).toFixed(1)}%${isGlobal ? "*" : ""}`}
                              </td>
                            );
                          })}
                          <td style={{ padding: "0.3rem 0.5rem", fontSize: "0.78rem", textAlign: "right", color: "var(--text-2)" }}>
                            {row.maxRows}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          );
        })()}
        </div>
      </Section>

      <Section
        title="Ensemble — heurystyka vs ML"
        subtitle="Porównanie głosów, tryb mieszany i leaderboard kto historycznie wygrywa."
      >
        {/* ── Selektor trybu ── */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.82rem", color: "var(--text-2)", fontWeight: 500 }}>Tryb sygnału:</span>
          {[
            { value: "heuristic",          label: "Tylko heurystyka" },
            { value: "ml",                 label: "Tylko ML" },
            { value: "ensemble_weighted",  label: "Ensemble ważony" },
            { value: "ensemble_majority",  label: "Ensemble większościowy" },
          ].map(m => (
            <button key={m.value} onClick={() => { setEnsembleMode(m.value); refresh(); }}
              style={{ padding: "0.3rem 0.7rem", borderRadius: "6px", fontSize: "0.82rem", cursor: "pointer",
                border: ensembleMode === m.value ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                background: ensembleMode === m.value ? "var(--bg-hover)" : "var(--bg-card)",
                color: "var(--text)",
                fontWeight: ensembleMode === m.value ? 600 : 400,
              }}>{m.label}</button>
          ))}
        </div>

        {ensembleSignal ? (
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            {/* ── Głosy osobno ── */}
            <div style={{ flex: "1 1 360px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.5rem" }}>
                Głosy systemów
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {ensembleSignal.votes.map(v => {
                  const dirColor = v.direction === "up" ? "#16a34a" : v.direction === "down" ? "#dc2626" : "#b45309";
                  const dirIcon = v.direction === "up" ? "▲" : v.direction === "down" ? "▼" : "●";
                  return (
                    <div key={v.source} style={{ padding: "0.5rem 0.7rem", borderRadius: "8px",
                      border: `1px solid ${v.available ? "var(--border)" : "var(--border)"}`,
                      background: v.available ? "var(--bg-card)" : "var(--bg-subtle)",
                      opacity: v.available ? 1 : 0.6,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontWeight: 600, fontSize: "0.83rem" }}>{v.source_label}</span>
                        {v.available ? (
                          <span style={{ color: dirColor, fontWeight: 700, fontSize: "0.9rem" }}>
                            {dirIcon} {v.direction.toUpperCase()}
                          </span>
                        ) : <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>brak modelu</span>}
                      </div>
                      {v.available && (
                        <>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.25rem" }}>
                            <div style={{ flex: 1, height: "6px", background: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                              <div style={{ width: `${v.probability_up.toFixed(0)}%`, height: "100%", background: dirColor, borderRadius: "3px" }} />
                            </div>
                            <span style={{ fontSize: "0.72rem", color: dirColor, fontWeight: 500, minWidth: "45px" }}>
                              p(↑)={v.probability_up.toFixed(1)}%
                            </span>
                            <span style={{ fontSize: "0.7rem", color: "var(--text-2)" }}>
                              conf={v.confidence.toFixed(0)}%
                            </span>
                          </div>
                          <div style={{ fontSize: "0.68rem", color: "var(--text-2)", marginTop: "0.2rem" }}>{v.reasoning}</div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── Wynik zbiorczy ── */}
            <div style={{ flex: "1 1 260px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.5rem" }}>
                Wynik {ensembleSignal.mode_label}
              </div>
              {(() => {
                const dir = ensembleSignal.final_direction;
                const col = dir === "up" ? "#16a34a" : dir === "down" ? "#dc2626" : "#b45309";
                const bg  = dir === "up" ? "rgba(22,163,74,0.07)" : dir === "down" ? "rgba(220,38,38,0.07)" : "rgba(180,87,9,0.06)";
                const actionColor = ensembleSignal.action === "KUP" ? "#16a34a" : ensembleSignal.action === "SPRZEDAJ" ? "#dc2626" : "#b45309";
                return (
                  <div style={{ padding: "0.75rem", borderRadius: "10px", border: `1.5px solid ${col}`, background: bg }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                      <span style={{ fontSize: "2rem", color: col }}>
                        {dir === "up" ? "▲" : dir === "down" ? "▼" : "●"}
                      </span>
                      <div>
                        <span style={{ fontWeight: 700, fontSize: "1.1rem", color: col }}>{dir.toUpperCase()}</span>
                        <span style={{ marginLeft: "0.75rem", padding: "0.2rem 0.55rem", borderRadius: "5px",
                          background: `${actionColor}18`, color: actionColor, fontWeight: 700, fontSize: "0.83rem",
                          border: `1px solid ${actionColor}33` }}>
                          {ensembleSignal.action}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
                      <div style={{ flex: 1, height: "8px", background: "var(--bg-subtle)", borderRadius: "4px", overflow: "hidden" }}>
                        <div style={{ width: `${ensembleSignal.final_probability_up.toFixed(0)}%`, height: "100%", background: col, borderRadius: "4px" }} />
                      </div>
                      <span style={{ fontSize: "0.78rem", color: col, fontWeight: 600 }}>p(↑)={ensembleSignal.final_probability_up.toFixed(1)}%</span>
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginBottom: "0.25rem" }}>
                      Pewność: {ensembleSignal.final_confidence.toFixed(0)}% &nbsp;|&nbsp; Konsensus: <strong>{ensembleSignal.consensus}</strong> ({(ensembleSignal.consensus_score*100).toFixed(0)}%)
                    </div>
                    {ensembleSignal.mode === "ensemble_weighted" && (
                      <div style={{ fontSize: "0.7rem", color: "var(--text-3)" }}>
                        Wagi: heurystyka {(ensembleSignal.heuristic_weight*100).toFixed(0)}% / ML {(ensembleSignal.ml_weight*100).toFixed(0)}%
                      </div>
                    )}
                    <div style={{ fontSize: "0.73rem", color: "var(--text-2)", marginTop: "0.4rem", lineHeight: 1.5 }}>
                      {ensembleSignal.rationale}
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        ) : (
          <p className="long-text">Brak sygnału ensemble. Odśwież dane.</p>
        )}

        {/* ── Leaderboard ── */}
        {ensembleLeaderboard.length > 0 && (
          <>
            <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.5rem" }}>
              Leaderboard — kto historycznie wygrywa
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.79rem" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)" }}>
                    {["Aktywo","Rekordów","Heurystyka %","ML %","Ensemble %","Remisy","Zalecany tryb","Śr. conf H","Śr. conf ML"].map(h => (
                      <th key={h} style={{ padding: "0.3rem 0.5rem", textAlign: "left", fontWeight: 600, fontSize: "0.72rem", color: "var(--text-2)", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ensembleLeaderboard.map(row => {
                    const best = Math.max(row.heuristic_win_rate, row.ml_win_rate, row.ensemble_win_rate);
                    const modeColors: Record<string,string> = { heuristic:"#4f86f7", ml:"#22c55e", ensemble_weighted:"#f59e0b", ensemble_majority:"#a855f7" };
                    const modeLabels: Record<string,string> = { heuristic:"Heurystyka", ml:"ML", ensemble_weighted:"Ensemble ważony", ensemble_majority:"Ensemble większościowy" };
                    const winCell = (rate: number, key: string) => (
                      <td key={key} style={{ padding: "0.3rem 0.5rem", fontWeight: rate === best && rate > 0 ? 700 : 400,
                        color: rate === best && rate > 0 ? "#16a34a" : "inherit" }}>
                        {row.total_records > 0 ? `${(rate*100).toFixed(0)}%` : "—"}
                      </td>
                    );
                    return (
                      <tr key={row.asset_id} style={{ borderBottom: "1px solid var(--border)", background: row.asset_id === selectedAsset ? "var(--bg-hover)" : undefined, cursor: "pointer" }}
                        onClick={() => setSelectedAsset(row.asset_id)}>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: 600 }}>{row.name}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.total_records}</td>
                        {winCell(row.heuristic_win_rate, "h")}
                        {winCell(row.ml_win_rate, "ml")}
                        {winCell(row.ensemble_win_rate, "ens")}
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.ties}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>
                          <span style={{ padding: "0.15rem 0.45rem", borderRadius: "4px", fontSize: "0.72rem",
                            background: `${modeColors[row.recommended_mode] ?? "#888"}18`,
                            color: modeColors[row.recommended_mode] ?? "inherit", fontWeight: 500 }}>
                            {modeLabels[row.recommended_mode] ?? row.recommended_mode}
                          </span>
                        </td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.avg_heuristic_confidence.toFixed(0)}%</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.avg_ml_confidence.toFixed(0)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-2)", marginTop: "0.5rem" }}>
              Leaderboard wypełnia się po tym jak ensemble records dostaną outcomes (po ~5 dniach od zapisania sygnału).
              Używaj "Ensemble ważony" dopóki leaderboard nie wskaże wyraźnego zwycięzcy.
            </p>
          </>
        )}
      </Section>

      <Section
        title="Tabela rekomendacji"
        subtitle="Syntetyczna rekomendacja KUP / SPRZEDAJ / TRZYMAJ dla każdego aktywa na podstawie wszystkich dostępnych sygnałów."
      >
        {recommendations.length === 0 ? (
          <p className="long-text">Brak danych. Kliknij Odśwież aby załadować rekomendacje.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem", tableLayout: "auto" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)" }}>
                  {[
                    ["Aktywo","symbol","Symbol giełdowy i nazwa spółki"],
                    ["Rekomendacja","recommendation","Syntetyczna rekomendacja: KUP (composite>62), SPRZEDAJ (<38), TRZYMAJ (środek). Wynika z 13 ważonych sygnałów."],
                    ["Wynik","composite_score","Wynik kompozytowy 0–100. Powyżej 62 = KUP, poniżej 38 = SPRZEDAJ. Ważona suma: trend 18%, prognoza 5d 15%, conviction 12%, ryzyko 10% i inne."],
                    ["Pewność","confidence","Odległość od neutralnego 50 w obie strony. 100% = maksymalna pewność kierunku, 0% = brak sygnału."],
                    ["Trend","trend_score","Siła trendu cenowego od −100 (silny spadek) do +100 (silny wzrost). Liczone z EMA20/50/200 i momentum."],
                    ["Sent.","sentiment_score","Wynik sentymentu newsów od −100 do +100. Bazuje na NLP (FinBERT lub heurystyka keyword-based)."],
                    ["Kruchość","fragility_score","Miara niestabilności układu — wysokość wahań, rozbieżność sygnałów, zmienność sentymentu. >60 = ostrzeżenie."],
                    ["Reżim","regime","Aktualny reżim rynkowy: trending_up, trending_down, ranging, volatile. Ustalany przez kombinator sygnałów."],
                    ["Prog 5d","forecast_up_5d","Prawdopodobieństwo wzrostu ceny w ciągu 5 dni roboczych wg modelu heurystycznego. >50% = bullish."],
                    ["Prog 20d","forecast_up_20d","Prawdopodobieństwo wzrostu w ciągu 20 dni (1 miesiąc). Horyzont długoterminowy."],
                    ["Conv.","conviction_score","Conviction score z decision support 0–100. Siła przekonania o kierunku ruchu — im wyższy tym bardziej zdecydowany sygnał."],
                    ["Ryzyko","risk_score","Poziom ryzyka 0–100 z decision support. Wyższy = bardziej niebezpieczna pozycja. Uwzględnia kruchość, zmienność i dywergencje."],
                    ["ML 5d","ml_prob_up","Prawdopodobieństwo wzrostu za 5 dni wg modelu ML (Logistic Regression). Dostępne po wytrenowaniu modelu."],
                    ["Trafn. hist.","directional_accuracy","Historyczna trafność kierunkowa tez dla tego aktywa w %. Liczone z zamkniętych outcomes. >55% = model działa."],
                    ["Alerty","active_alerts","Liczba aktywnych alertów. ⚠ = alert krytyczny (fragility, degradacja prognozy). Wpływa negatywnie na wynik kompozytowy."],
                  ].map(([label, key, tip]) => (
                    <SortTh key={key} tableId="recommendations" colKey={key} label={label} tip={tip} side="bottom"
                      style={{ padding: "0.3rem 0.35rem", fontSize: "0.72rem", color: "var(--text-2)", whiteSpace: "nowrap" }} />
                  ))}
                  <th style={{ padding: "0.3rem 0.35rem", fontSize: "0.72rem", color: "var(--text-2)" }}>Sygnały</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows("recommendations", recommendations as unknown as Record<string,unknown>[]).map((r_raw) => { const r = r_raw as typeof recommendations[0];
                  const recColor = r.recommendation === "KUP" ? "#16a34a" : r.recommendation === "SPRZEDAJ" ? "#dc2626" : "#b45309";
                  const recBg   = r.recommendation === "KUP" ? "rgba(22,163,74,0.08)" : r.recommendation === "SPRZEDAJ" ? "rgba(220,38,38,0.08)" : "rgba(180,87,9,0.07)";
                  const scoreBar = (val: number, neutral = 50) => {
                    const pct = Math.abs(val - neutral) / neutral * 100;
                    const col = val > neutral ? "#16a34a" : "#dc2626";
                    return (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
                        <div style={{ width: "28px", height: "5px", background: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                          <div style={{ width: `${Math.min(pct, 100).toFixed(0)}%`, height: "100%", background: col, borderRadius: "3px" }} />
                        </div>
                        <span style={{ color: val > neutral ? "#16a34a" : "#dc2626" }}>{val.toFixed(1)}</span>
                      </div>
                    );
                  };
                  const dirIcon = (dir: string | null) => dir === "up" ? <span style={{ color: "#16a34a" }}>▲</span> : dir === "down" ? <span style={{ color: "#dc2626" }}>▼</span> : <span style={{ color: "var(--text-3)" }}>—</span>;
                  const pct = (v: number | null) => v != null ? `${v.toFixed(1)}%` : "—";
                  return (
                    <tr
                      key={r.asset_id}
                      style={{
                        borderBottom: "1px solid var(--border)",
                        background: r.asset_id === selectedAsset ? "var(--bg-hover)" : undefined,
                        cursor: "pointer",
                      }}
                      onClick={() => setSelectedAsset(r.asset_id)}
                    >
                      <td style={{ padding: "0.25rem 0.35rem", fontWeight: 600 }}>
                        {r.symbol}
                        <div style={{ fontSize: "0.68rem", color: "var(--text-2)", fontWeight: 400 }}>{r.name}</div>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        <span style={{
                          display: "inline-block",
                          padding: "0.2rem 0.55rem",
                          borderRadius: "5px",
                          fontWeight: 700,
                          fontSize: "0.78rem",
                          background: recBg,
                          color: recColor,
                          border: `1px solid ${recColor}33`,
                          letterSpacing: "0.03em",
                        }}>
                          {r.recommendation}
                        </span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{scoreBar(r.composite_score)}</td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.75rem", color: "var(--text-2)" }}>
                        {r.confidence.toFixed(0)}%
                        <div style={{ fontSize: "0.65rem" }}>{r.confidence_label}</div>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{scoreBar(r.trend_score + 50, 50)}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{scoreBar(r.sentiment_score + 50, 50)}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        <span style={{ color: r.fragility_score > 60 ? "#dc2626" : r.fragility_score > 35 ? "#b45309" : "#16a34a" }}>
                          {r.fragility_score.toFixed(1)}
                        </span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.72rem", maxWidth: "80px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.regime}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        {dirIcon(r.forecast_dir_5d)}
                        <span style={{ fontSize: "0.72rem", marginLeft: "0.2rem", color: "var(--text-2)" }}>{pct(r.forecast_up_5d)}</span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        {dirIcon(r.forecast_dir_20d)}
                        <span style={{ fontSize: "0.72rem", marginLeft: "0.2rem", color: "var(--text-2)" }}>{pct(r.forecast_up_20d)}</span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>{r.conviction_score?.toFixed(1) ?? "—"}</td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        <span style={{ color: (r.risk_score ?? 50) > 60 ? "#dc2626" : "inherit" }}>
                          {r.risk_score?.toFixed(1) ?? "—"}
                        </span>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        {r.ml_prediction ? (
                          <span style={{ color: r.ml_prediction === "up" ? "#16a34a" : "#dc2626", fontWeight: 500 }}>
                            {r.ml_prediction === "up" ? "▲" : "▼"} {pct(r.ml_prob_up)}
                          </span>
                        ) : <span style={{ color: "var(--text-3)" }}>—</span>}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.75rem" }}>
                        {r.directional_accuracy != null ? `${r.directional_accuracy.toFixed(1)}%` : "—"}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem" }}>
                        {r.active_alerts > 0 ? (
                          <span style={{ color: r.has_critical_alert ? "#dc2626" : "#b45309", fontWeight: 600 }}>
                            {r.active_alerts} {r.has_critical_alert ? "⚠" : ""}
                          </span>
                        ) : <span style={{ color: "var(--text-3)" }}>—</span>}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", maxWidth: "160px" }}>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-2)", lineHeight: 1.4 }}>
                          {r.top_signals.slice(0, 3).map(s => (
                            <span key={s.name} style={{
                              display: "inline-block",
                              marginRight: "0.25rem",
                              marginBottom: "0.1rem",
                              padding: "0.1rem 0.3rem",
                              borderRadius: "3px",
                              fontSize: "0.65rem",
                              background: s.direction === "bullish" ? "rgba(22,163,74,0.1)" : s.direction === "bearish" ? "rgba(220,38,38,0.1)" : "var(--bg-card)",
                              color: s.direction === "bullish" ? "#15803d" : s.direction === "bearish" ? "#b91c1c" : "inherit",
                            }}>{s.name}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Uzasadnienie dla wybranego aktywa */}
            {(() => {
              const sel = recommendations.find(r => r.asset_id === selectedAsset);
              if (!sel) return null;
              return (
                <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", borderRadius: "8px", background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: "0.83rem" }}>
                  <strong style={{ marginRight: "0.5rem" }}>{sel.symbol} — uzasadnienie:</strong>
                  {sel.rationale}
                  {sel.action_label && (
                    <span style={{ marginLeft: "0.75rem", padding: "0.15rem 0.5rem", borderRadius: "4px", background: "var(--bg-hover)", fontSize: "0.75rem" }}>
                      Status: {sel.action_label}
                    </span>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </Section>

      <Section
        title="Jakość danych"
        subtitle="Monitoring brakujących danych, stale'ów, błędów providerów i coverage ML per aktywo."
      >
        {!dataQuality ? (
          <p className="long-text">Ładowanie raportu jakości…</p>
        ) : (
          <>
            {/* ── Summary cards ── */}
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              {[
                { label: "Aktywów", value: String(dataQuality.summary.total_assets ?? 0), color: "inherit" },
                { label: "Z problemami", value: String(dataQuality.summary.assets_with_issues ?? 0), color: (dataQuality.summary.assets_with_issues as number) > 0 ? "#dc2626" : "#16a34a" },
                { label: "Gotowych do ML", value: String(dataQuality.summary.assets_ready_for_ml ?? 0), color: "#16a34a" },
                { label: "Przestarz. ceny", value: String(dataQuality.summary.stale_prices ?? 0), color: (dataQuality.summary.stale_prices as number) > 0 ? "#b45309" : "inherit" },
                { label: "Błędy sync 24h", value: String(dataQuality.summary.sync_errors_24h ?? 0), color: (dataQuality.summary.sync_errors_24h as number) > 0 ? "#dc2626" : "inherit" },
                { label: "Śr. wynik", value: ((dataQuality.summary.avg_overall_score as number) * 100).toFixed(0) + "%", color: "inherit" },
              ].map(c => (
                <div key={c.label} style={{ padding: "0.5rem 0.9rem", borderRadius: "8px", border: "1px solid var(--border)", background: "var(--bg-card)", minWidth: "100px", textAlign: "center" }}>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: c.color }}>{c.value}</div>
                  <div style={{ fontSize: "0.72rem", color: "var(--text-2)" }}>{c.label}</div>
                </div>
              ))}
            </div>

            {/* ── Grade distribution ── */}
            {(() => {
              const grades = (dataQuality.summary.grade_distribution ?? {}) as Record<string,number>;
              const gradeColors: Record<string,string> = { A:"#16a34a", B:"#65a30d", C:"#b45309", D:"#ea580c", F:"#dc2626" };
              return (
                <div style={{ display: "flex", gap: "0.4rem", marginBottom: "1rem" }}>
                  {["A","B","C","D","F"].map(g => {
                    const count = grades[g] ?? 0;
                    if (count === 0) return null;
                    return (
                      <span key={g} style={{ padding: "0.2rem 0.6rem", borderRadius: "6px", background: `${gradeColors[g]}18`, border: `1px solid ${gradeColors[g]}44`, color: gradeColors[g], fontWeight: 700, fontSize: "0.82rem" }}>
                        {g}: {count}
                      </span>
                    );
                  })}
                </div>
              );
            })()}

            {/* ── Per-asset table ── */}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.79rem" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)" }}>
                    {[
                      ["Aktywo","symbol","Symbol i nazwa aktywa"],
                      ["Ocena","grade","Ocena ogólna jakości danych: A (>80%), B (>60%), C (>40%), D (>20%), F (<20%). Ważona: ceny 30%, features 25%, newsy 20%, ML 15%, sync 10%."],
                      ["Wynik","overall_score","Wynik ogólny 0–100% na podstawie 5 wymiarów jakości."],
                      ["Ceny","prices.total_points","Łączna liczba punktów cenowych w bazie. Min. ~60 dla sensownego ML. Zielone gdy ostatnia cena <48h temu."],
                      ["Newsy","news.total_items","Całkowita liczba newsów oraz liczba z ostatnich 7 dni. Newsy są źródłem sentymentu i narracji."],
                      ["NLP%","news.nlp_coverage_pct","Odsetek newsów które przeszły przez NLP (FinBERT/heurystykę). <30% = ostrzeżenie — uruchom Napraw asset."],
                      ["Features","features.has_snapshot","Czy istnieje i czy jest aktualny snapshot feature'ów (trend, sentyment, reżim). Przestarzały = >52h."],
                      ["ML rows","ml.training_rows","Łączna liczba wierszy w ML training dataset dla tego aktywa. Potrzeba ~120 labeled rows do treningu."],
                      ["Label%","ml.label_coverage_pct","Odsetek wierszy z wypełnionymi etykietami (target_up_5d/20d). Etykiety z cen historycznych — <20% = za mało historii."],
                      ["Sync err 24h","sync.errors_24h","Liczba błędów konfiguracyjnych sync w ostatnich 24h (rate-limity nie liczą się). >5 = sprawdź klucze API."],
                    ].map(([label, key, tip]) => (
                      <SortTh key={key} tableId="dataquality" colKey={key} label={label} tip={tip} side="bottom"
                        style={{ padding: "0.35rem 0.5rem", fontSize: "0.73rem", color: "var(--text-2)" }} />
                    ))}
                    <th style={{ padding: "0.35rem 0.5rem", fontSize: "0.73rem", color: "var(--text-2)" }}>Problemy</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows("dataquality",
                    dataQuality.assets.map(a => ({
                      ...a,
                      "prices.total_points": a.prices.total_points,
                      "news.total_items": a.news.total_items,
                      "news.nlp_coverage_pct": a.news.nlp_coverage_pct,
                      "features.has_snapshot": a.features.has_snapshot ? 1 : 0,
                      "ml.training_rows": a.ml.training_rows,
                      "ml.label_coverage_pct": a.ml.label_coverage_pct,
                      "sync.errors_24h": a.sync.errors_24h,
                    })) as unknown as Record<string,unknown>[]
                  ).map(a_raw => {
                    const a = a_raw as typeof dataQuality.assets[0];
                    const gradeColor: Record<string,string> = { A:"#16a34a", B:"#65a30d", C:"#b45309", D:"#ea580c", F:"#dc2626" };
                    const col = gradeColor[a.grade] ?? "inherit";
                    const scoreBar = (s: number) => (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <div style={{ width: "36px", height: "6px", background: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                          <div style={{ width: `${(s*100).toFixed(0)}%`, height:"100%", background: s>=0.7?"#16a34a":s>=0.4?"#b45309":"#dc2626", borderRadius:"3px" }} />
                        </div>
                        <span style={{ fontSize:"0.7rem", color:"var(--text-2)" }}>{(s*100).toFixed(0)}%</span>
                      </div>
                    );
                    const staleTag = (stale: boolean) => stale
                      ? <span style={{ color:"#dc2626", fontSize:"0.68rem" }}>●przestarz.</span>
                      : <span style={{ color:"#16a34a", fontSize:"0.68rem" }}>●ok</span>;
                    return (
                      <tr key={a.asset_id} style={{ borderBottom:"1px solid var(--border)", background: a.asset_id===selectedAsset?"var(--bg-hover)":undefined, cursor:"pointer" }} onClick={() => setSelectedAsset(a.asset_id)}>
                        <td style={{ padding:"0.35rem 0.5rem", fontWeight:600 }}>
                          {a.symbol}
                          <div style={{ fontSize:"0.65rem", color:"var(--text-2)", fontWeight:400 }}>{a.name}</div>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <span style={{ fontWeight:700, color:col, fontSize:"1rem" }}>{a.grade}</span>
                          <span style={{ fontSize:"0.68rem", color:"var(--text-2)", marginLeft:"0.25rem" }}>{a.grade_label}</span>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>{scoreBar(a.overall_score)}</td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <div>{a.prices.total_points}pkt</div>
                          {staleTag(a.prices.is_stale)}
                          {a.prices.gap_pct > 10 && <div style={{ fontSize:"0.65rem", color:"#b45309" }}>luki {a.prices.gap_pct.toFixed(0)}%</div>}
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <div>{a.news.total_items} ({a.news.items_7d} w 7d)</div>
                          {staleTag(a.news.is_stale)}
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <span style={{ color: a.news.nlp_coverage_pct>=70?"#16a34a":a.news.nlp_coverage_pct>=30?"#b45309":"#dc2626" }}>
                            {a.news.nlp_coverage_pct.toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          {a.features.has_snapshot
                            ? <>{staleTag(a.features.is_stale)}{!a.features.has_all_forecasts && <div style={{ fontSize:"0.65rem", color:"#b45309" }}>brak 1/3 fc</div>}</>
                            : <span style={{ color:"#dc2626", fontSize:"0.72rem" }}>brak</span>}
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <div>{a.ml.training_rows}</div>
                          {a.ml.ready_for_training
                            ? <span style={{ fontSize:"0.65rem", color:"#16a34a" }}>●gotowy</span>
                            : <span style={{ fontSize:"0.65rem", color:"var(--text-3)" }}>●za mało</span>}
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <span style={{ color: a.ml.label_coverage_pct>=60?"#16a34a":a.ml.label_coverage_pct>=20?"#b45309":"#dc2626" }}>
                            {a.ml.label_coverage_pct.toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }}>
                          <span style={{ color: a.sync.errors_24h>0?"#dc2626":"inherit", fontWeight: a.sync.errors_24h>0?700:400 }}>
                            {a.sync.errors_24h}
                          </span>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem", maxWidth:"200px" }}>
                          {a.issues.slice(0,2).map((issue, i) => (
                            <div key={i} style={{ fontSize:"0.65rem", color:"#dc2626", lineHeight:1.4 }}>⚠ {issue}</div>
                          ))}
                          {a.warnings.slice(0,1).map((w, i) => (
                            <div key={i} style={{ fontSize:"0.65rem", color:"#b45309", lineHeight:1.4 }}>△ {w}</div>
                          ))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Section>

      <Section
        title="Skuteczność: heurystyka vs ML"
        subtitle="Porównanie trafności heurystyki i modelu ML."
      >
        <div className="grid-3">
          <Panel title="Ostatnie porównanie">
            {strategyComparison ? (
              <>
                <MetaRow
                  label="Trafność heurystyki 5d"
                  value={formatPct(strategyComparison.heuristic_accuracy_5d * 100)}
                />
                <MetaRow
                  label="Trafność ML 5d"
                  value={formatPct(strategyComparison.ml_accuracy_5d * 100)}
                />
                <MetaRow
                  label="Śr. zwrot heurystyki 5d"
                  value={strategyComparison.heuristic_avg_return_5d.toFixed(3)}
                />
                <MetaRow
                  label="Śr. zwrot ML 5d"
                  value={strategyComparison.ml_avg_return_5d.toFixed(3)}
                />
                <MetaRow
                  label="Lepszy tryb"
                  value={strategyComparison.better_mode === "ml" ? "ML" : strategyComparison.better_mode === "heuristic" ? "Heurystyka" : strategyComparison.better_mode}
                />
                <MetaRow
                  label="Próba"
                  value={String(strategyComparison.sample_size)}
                />
              </>
            ) : (
              <p className="long-text">
                Brak porównania dla wybranego aktywa.
              </p>
            )}
          </Panel>

          <Panel title="Walk-forward backtest">
            {walkForwardResult ? (() => {
              let parsed: any = null;
              try { parsed = JSON.parse(walkForwardResult.result_json); } catch { /* ignore */ }
              const models: Record<string, any> = parsed?.models ?? {};
              const ens = parsed?.ensemble ?? null;
              const MODEL_SHORT: Record<string, string> = {
                logistic_regression: "LR", random_forest: "RF", xgboost: "XGB", lstm: "LSTM",
              };
              const fmtPct = (v: number | undefined) => v != null ? `${(v * 100).toFixed(1)}%` : "—";
              const metricColor = (v: number | undefined): React.CSSProperties =>
                !v ? {} : { color: v >= 0.55 ? "#16a34a" : v >= 0.5 ? "inherit" : "#dc2626", fontWeight: v >= 0.55 ? 600 : 400 };
              const thS: React.CSSProperties = { padding: "0.3rem 0.5rem", fontSize: "0.74rem", fontWeight: 600, color: "var(--text-2)", textAlign: "left", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
              const tdS: React.CSSProperties = { padding: "0.3rem 0.5rem", fontSize: "0.78rem", textAlign: "right" };
              return (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <div style={{ fontSize: "0.74rem", color: "var(--text-3)" }}>
                    {new Date(walkForwardResult.created_at).toLocaleString("pl-PL")}
                    {parsed?.asset_id && ` · ${parsed.asset_id.toUpperCase()}`}
                    {parsed?.total_rows && ` · ${parsed.total_rows} wierszy`}
                    {ens?.windows && ` · ${ens.windows} okien`}
                  </div>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th style={{ ...thS, textAlign: "left" }}>Model</th>
                          <th style={{ ...thS, textAlign: "right" }}>Accuracy</th>
                          <th style={{ ...thS, textAlign: "right" }}>Precision</th>
                          <th style={{ ...thS, textAlign: "right" }}>Recall</th>
                          <th style={{ ...thS, textAlign: "right" }}>F1</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(models).map(([name, m]: [string, any]) => (
                          <tr key={name} style={{ borderBottom: "1px solid var(--border)" }}>
                            <td style={{ ...tdS, textAlign: "left", fontWeight: 500 }}>
                              {MODEL_SHORT[name] ?? name}{m.is_global ? <span style={{ color: "var(--text-3)", fontWeight: 400 }}> *</span> : null}
                            </td>
                            <td style={{ ...tdS, ...metricColor(m.avg_accuracy) }}>{fmtPct(m.avg_accuracy)}</td>
                            <td style={{ ...tdS, ...metricColor(m.avg_precision) }}>{fmtPct(m.avg_precision)}</td>
                            <td style={{ ...tdS, ...metricColor(m.avg_recall) }}>{fmtPct(m.avg_recall)}</td>
                            <td style={{ ...tdS, ...metricColor(m.avg_f1) }}>{fmtPct(m.avg_f1)}</td>
                          </tr>
                        ))}
                        {ens && ens.windows > 0 && (
                          <tr style={{ borderTop: "2px solid var(--border)", background: "var(--bg-subtle)" }}>
                            <td style={{ ...tdS, textAlign: "left", fontWeight: 700 }}>Ensemble</td>
                            <td style={{ ...tdS, ...metricColor(ens.avg_accuracy) }}>{fmtPct(ens.avg_accuracy)}</td>
                            <td style={{ ...tdS, ...metricColor(ens.avg_precision) }}>{fmtPct(ens.avg_precision)}</td>
                            <td style={{ ...tdS, ...metricColor(ens.avg_recall) }}>{fmtPct(ens.avg_recall)}</td>
                            <td style={{ ...tdS, ...metricColor(ens.avg_f1) }}>{fmtPct(ens.avg_f1)}</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })() : (
              <p className="long-text">
                Uruchom walk-forward backtest, aby zobaczyć wynik.
              </p>
            )}
          </Panel>

          <Panel title="Interpretacja">
            <p className="long-text">
              Heurystyka i ML są porównywane równolegle. Dzięki temu możesz
              ocenić, czy model już daje przewagę, czy nadal lepiej polegać na
              warstwie heurystycznej.
            </p>
          </Panel>
        </div>

        <div className="spacer" />

        <Panel title="Wszystkie porównania">
          <DataTable
            columns={["Aktywo","Trafność heuryst.","Trafność ML","Zwrot heuryst.","Zwrot ML","Lepszy tryb","Próba"]}
            rows={allComparisons.map((row) => ({
              "Aktywo": row.asset_id,
              "Trafność heuryst.": formatPct(row.heuristic_accuracy_5d * 100),
              "Trafność ML": formatPct(row.ml_accuracy_5d * 100),
              "Zwrot heuryst.": row.heuristic_avg_return_5d.toFixed(3),
              "Zwrot ML": row.ml_avg_return_5d.toFixed(3),
              "Lepszy tryb": row.better_mode,
              "Próba": String(row.sample_size),
            }))}
          />
        </Panel>
      </Section>

      <Section
        title="Zarządzanie aktywami"
        subtitle="Dodawaj i usuwaj aktywa. Konfiguruj symbole do synchronizacji danych."
      >
        <div className="grid-2">
          {/* ── Lista aktywów z opcją usunięcia ── */}
          <Panel title="Aktywne aktywa">
            <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginBottom: "0.75rem" }}>
              {assets.map((a) => (
                <div key={a.id} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "0.45rem 0.65rem", borderRadius: "7px",
                  border: a.id === selectedAsset ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                  background: a.id === selectedAsset ? "var(--bg-hover)" : "var(--bg-card)",
                }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>
                      {a.symbol} — {a.name}
                      <span style={{ marginLeft: "0.4rem", fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 400 }}>
                        [{a.type}]
                      </span>
                    </span>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-2)" }}>
                      {a.price_symbol ? `cena: ${a.price_symbol}` : a.metal_price_fn ? `metal fn: ${a.metal_price_fn}` : "brak symbolu ceny"}
                      {" · news: "}{a.news_term ?? a.name}
                    </span>
                  </div>
                  <button
                    title="Usuń aktywo"
                    onClick={() => deleteAssetNow(a.id)}
                    style={{
                      background: "none", border: "none", cursor: "pointer",
                      color: "var(--bad)", padding: "0.15rem 0.3rem",
                      borderRadius: "4px", display: "flex", alignItems: "center", gap: "0.2rem",
                      fontSize: "0.75rem",
                    }}
                  >
                    <Trash2 size={13} /> Usuń
                  </button>
                </div>
              ))}
            </div>
            <button className="secondary-button" onClick={() => setShowAddAsset((v) => !v)}>
              <WandSparkles size={16} />
              {showAddAsset ? "Anuluj" : "Dodaj nowe aktywo"}
            </button>
          </Panel>

          {/* ── Formularz dodawania ── */}
          <Panel title="Dodaj aktywo">
            {showAddAsset ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {([
                  ["id",             "ID (np. amzn)",            "text",   "id"],
                  ["symbol",         "Symbol giełdowy (np. AMZN)", "text", "symbol"],
                  ["name",           "Pełna nazwa",              "text",   "name"],
                  ["sector",         "Sektor (opcjonalnie)",     "text",   "sector"],
                  ["price_symbol",   "Cena: symbol Alpha Vantage", "text", "price_symbol"],
                  ["news_symbol",    "Newsy: symbol Finnhub (akcje)", "text", "news_symbol"],
                  ["news_term",      "Newsy: termin wyszukiwania", "text", "news_term"],
                  ["metal_price_fn", "Metal: fn Alpha Vantage (np. GOLD)", "text", "metal_price_fn"],
                ] as [string, string, string, keyof typeof newAsset][]).map(([field, label]) => (
                  <div key={field} style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <label style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 500 }}>{label}</label>
                    <input
                      type="text"
                      value={String(newAsset[field as keyof typeof newAsset] ?? "")}
                      onChange={(e) => setNewAsset((prev) => ({ ...prev, [field]: e.target.value }))}
                      style={{
                        padding: "0.35rem 0.55rem", borderRadius: "6px",
                        border: "1px solid var(--border)", background: "var(--bg-card)",
                        color: "var(--text)", fontSize: "0.83rem",
                        outline: "none",
                      }}
                    />
                  </div>
                ))}

                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.25rem" }}>
                  <label style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 500 }}>Typ:</label>
                  <select
                    value={newAsset.type}
                    onChange={(e) => setNewAsset((prev) => ({ ...prev, type: e.target.value as "stock" | "metal" }))}
                    style={{
                      padding: "0.3rem 0.5rem", borderRadius: "6px",
                      border: "1px solid var(--border)", background: "var(--bg-card)",
                      color: "var(--text)", fontSize: "0.83rem",
                    }}
                  >
                    <option value="stock">stock</option>
                    <option value="metal">metal</option>
                  </select>
                </div>

                <div style={{ padding: "0.5rem 0.65rem", borderRadius: "6px", background: "var(--bg-subtle)", fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.25rem" }}>
                  <strong>Wskazówka:</strong> Dla akcji ustaw <em>price_symbol</em> (Alpha Vantage) i <em>news_symbol</em> (Finnhub). Dla metali ustaw <em>metal_price_fn</em> (np. GOLD, SILVER). <em>news_term</em> służy do wyszukiwania newsów gdy Finnhub nie jest dostępny.
                </div>

                <button className="primary-button" onClick={addAssetNow} style={{ marginTop: "0.25rem" }}>
                  <WandSparkles size={16} /> Dodaj aktywo
                </button>
              </div>
            ) : (
              <p className="long-text">
                Kliknij „Dodaj nowe aktywo" po lewej, aby otworzyć formularz.<br /><br />
                Po dodaniu aktywa możesz uruchomić jego bootstrap (przycisk „Bootstrap" w górnym pasku) aby pobrać ceny i newsy.
              </p>
            )}
          </Panel>
        </div>
      </Section>

      <Section
        title="Watchlisty i personalizacja"
        subtitle="Watchlisty, własne preferencje i szybkie akcje."
      >
        <div className="grid-2">
          <Panel title="Watchlisty">
            <div className="toolbar-row" style={{ marginBottom: "0.75rem" }}>
              <button className="secondary-button" onClick={createDefaultWatchlist}>
                <Star size={16} />
                Nowa watchlista
              </button>
              <button
                className="secondary-button"
                onClick={addSelectedToFirstWatchlist}
              >
                <Rows3 size={16} />
                Dodaj {selectedAsset} do pierwszej
              </button>
            </div>

            {watchlists.length === 0 ? (
              <p className="long-text">Brak watchlist. Utwórz pierwszą powyżej.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {watchlists.map((wl) => (
                  <div
                    key={wl.id}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      padding: "0.6rem 0.75rem",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem" }}>
                      <span style={{ fontWeight: 500, fontSize: "0.9rem" }}>
                        {wl.name}
                        {wl.is_default && (
                          <span style={{ marginLeft: "0.4rem", fontSize: "0.72rem", padding: "0.1rem 0.35rem", background: "var(--bg-hover)", borderRadius: "4px" }}>
                            domyślna
                          </span>
                        )}
                      </span>
                      <button
                        title="Usuń watchlistę"
                        onClick={async () => {
                          if (!confirm(`Usunąć watchlistę "${wl.name}"?`)) return;
                          await api.deleteWatchlist(wl.id);
                          setWatchlists((prev) => prev.filter((w) => w.id !== wl.id));
                          setInfo(`Usunięto watchlistę "${wl.name}".`);
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--bad)",
                          padding: "0.1rem 0.3rem",
                          borderRadius: "4px",
                          fontSize: "0.8rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.25rem",
                        }}
                      >
                        <Trash2 size={14} /> Usuń listę
                      </button>
                    </div>

                    {wl.assets.length === 0 ? (
                      <p style={{ fontSize: "0.8rem", color: "var(--text-3)", margin: 0 }}>Pusta lista.</p>
                    ) : (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                        {wl.assets.map((assetId) => (
                          <span
                            key={assetId}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              padding: "0.2rem 0.5rem",
                              background: "var(--bg-card)",
                              border: "1px solid var(--border)",
                              borderRadius: "6px",
                              fontSize: "0.82rem",
                            }}
                          >
                            {assetId.toUpperCase()}
                            <button
                              title={`Usuń ${assetId}`}
                              onClick={async () => {
                                await api.removeAssetFromWatchlist(wl.id, assetId);
                                setWatchlists((prev) =>
                                  prev.map((w) =>
                                    w.id === wl.id
                                      ? { ...w, assets: w.assets.filter((a) => a !== assetId) }
                                      : w
                                  )
                                );
                                setInfo(`Usunięto ${assetId} z "${wl.name}".`);
                              }}
                              style={{
                                background: "none",
                                border: "none",
                                cursor: "pointer",
                                color: "var(--bad)",
                                padding: 0,
                                lineHeight: 1,
                                display: "flex",
                                alignItems: "center",
                              }}
                            >
                              <X size={12} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Powiadomienia - szybki setup">
            <div className="toolbar-row">
              <button className="secondary-button" onClick={createEmailChannelDemo}>
                <Mail size={16} />
                Dodaj demo email channel
              </button>
            </div>
            <p className="long-text">
              Adresy i numery docelowe możesz konfigurować przez endpointy
              notification channels. SMTP i Twilio/WhatsApp ustawiasz w{" "}
              <code>backend/.env</code>.
            </p>
          </Panel>
        </div>
      </Section>

      <Section
        title="Dashboard zbiorczy dla wielu aktywów"
        subtitle="Przegląd kilku aktywów naraz."
      >
        <DataTable
          columns={[
            "asset",
            "last_price",
            "trend_score",
            "sentiment_score",
            "fragility_score",
            "regime",
            "dominant_narrative",
          ]}
          rows={aggregateRows.map((row: any) => ({
            asset: row.asset?.symbol || row.asset?.id || "",
            last_price: fmtPrice(row.last_price, assetCurrencyMap.get(row.asset?.id) ?? "USD"),
            trend_score: row.trend_score,
            sentiment_score: row.sentiment_score,
            fragility_score: row.fragility_score,
            regime: row.regime,
            dominant_narrative: row.dominant_narrative,
          }))}
        />
      </Section>

      <Section
        title="Porównywarka aktywów"
        subtitle="Porównanie metryk między aktywami."
      >
        <div className="grid-2">
          <Panel title="Wybór aktywów do porównania">
            <p className="long-text" style={{ marginBottom: "0.75rem" }}>
              Zaznacz aktywa które chcesz porównać, następnie kliknij
              &ldquo;Odśwież&rdquo;.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              {assets.map((a) => {
                const checked = compareAssetIds.includes(a.id);
                return (
                  <label
                    key={a.id}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      padding: "0.3rem 0.65rem",
                      borderRadius: "6px",
                      border: checked ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                      background: checked ? "var(--bg-hover)" : "var(--bg-card)",
                      color: "var(--text)",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      fontWeight: checked ? 500 : 400,
                      userSelect: "none",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) =>
                        setCompareAssetIds((prev) =>
                          e.target.checked
                            ? [...prev, a.id]
                            : prev.filter((id) => id !== a.id)
                        )
                      }
                      style={{ margin: 0 }}
                    />
                    {a.name}
                  </label>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                className="secondary-button"
                onClick={() => setCompareAssetIds(assets.map((a) => a.id))}
              >
                Zaznacz wszystkie
              </button>
              <button
                className="secondary-button"
                onClick={() => setCompareAssetIds([])}
              >
                Wyczyść
              </button>
            </div>
          </Panel>

          <Panel title="Wyniki porównania">
            {compareRows.length === 0 ? (
              <p className="long-text">
                Zaznacz aktywa i kliknij &ldquo;Odśwież&rdquo;.
              </p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Aktywo","Cena","Trend","Sent.","Diverg.","Krhkość","Reżim","Narr.","Dir 1d","Conf 1d"].map((h) => (
                        <th key={h} style={{ padding: "0.35rem 0.5rem", textAlign: "left", fontWeight: 500, whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {compareRows.map((row) => {
                      const score = (v: number | null | undefined) =>
                        v == null ? "—" : v.toFixed(1);
                      const pct = (v: number | null | undefined) =>
                        v == null ? "—" : (v * 100).toFixed(0) + "%";
                      const dirColor = row.forecast_direction_1d === "up"
                        ? "#16a34a" : row.forecast_direction_1d === "down" ? "#dc2626" : "inherit";
                      return (
                        <tr
                          key={row.asset_id}
                          style={{ borderBottom: "1px solid var(--border)", background: row.asset_id === selectedAsset ? "var(--bg-hover)" : undefined }}
                        >
                          <td style={{ padding: "0.35rem 0.5rem", fontWeight: 500 }}>{row.asset_id.toUpperCase()}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{fmtPrice(row.last_price, assetCurrencyMap.get(row.asset_id) ?? "USD")}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{score(row.trend_score)}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{score(row.sentiment_score)}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{score(row.divergence_score)}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{score(row.fragility_score)}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{row.regime ?? "—"}</td>
                          <td style={{ padding: "0.35rem 0.5rem", maxWidth: "100px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.dominant_narrative ?? "—"}</td>
                          <td style={{ padding: "0.35rem 0.5rem", color: dirColor, fontWeight: 500 }}>{row.forecast_direction_1d ?? "—"}</td>
                          <td style={{ padding: "0.35rem 0.5rem" }}>{pct(row.forecast_confidence_1d)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      </Section>

      <Section
        title="Eksport PDF / raport dzienny"
        subtitle="Generowanie raportu dla aktywa lub watchlisty."
      >
        <div className="grid-2">
          <Panel title="Raport aktywa">
            <p className="long-text">
              Kliknij przycisk „Eksport PDF / raport dzienny”, aby wygenerować
              raport dla wybranego aktywa.
            </p>
            {lastReport ? (
              <>
                <MetaRow label="Nazwa pliku" value={lastReport.file_name} />
                <MetaRow label="Ścieżka pliku" value={lastReport.file_path} />
              </>
            ) : null}
          </Panel>

          <Panel title="Powiadomienia">
            <DataTable
              columns={["channel_type", "target", "label", "is_enabled"]}
              rows={channels}
            />
            <div className="spacer" />
            <DataTable
              columns={["event_type", "status", "message", "created_at"]}
              rows={events.slice(0, 10)}
            />
          </Panel>
        </div>
      </Section>

      <Section
        title="Alerty"
        subtitle="Alerty generowane automatycznie po każdym cyklu synchronizacji."
      >
        <div className="grid-2">
          <Panel title="Ostatnie alerty">
            {alerts.length === 0 ? (
              <p className="long-text">Brak alertów dla tego aktywa.</p>
            ) : (
              alerts.slice(0, 8).map((alert) => (
                <div key={alert.id} className="quality-block">
                  <div className="pill-row">
                    <Pill
                      tone={
                        alert.severity === "high"
                          ? "bad"
                          : alert.severity === "medium"
                          ? "warn"
                          : "good"
                      }
                    >
                      {alert.severity}
                    </Pill>
                    <Pill>{alert.alert_type}</Pill>
                    <Pill>{alert.status}</Pill>
                  </div>
                  <div
                    className="panel-title"
                    style={{ marginBottom: 6, fontSize: 15 }}
                  >
                    {alert.title}
                  </div>
                  <p className="long-text" style={{ marginTop: 0 }}>
                    {alert.message}
                  </p>
                </div>
              ))
            )}
          </Panel>

          <Panel title="Info o alertach">
            <p className="long-text">
              Alerty są obecnie generowane dla:
              <br />• dominant_narrative_changed
              <br />• fragility_high
              <br />• forecast_downgrade
            </p>
          </Panel>
        </div>
      </Section>

      <Section
        title="Bieżąca teza"
        subtitle="Aktualna teza inwestycyjna, kontrteza i warunki unieważnienia."
      >
        <div className="grid-2">
          <Panel title="Teza">
            <div className="pill-row">
              <Pill tone="good">{titleize(latestThesis?.dominant_narrative)}</Pill>
              <Pill>{titleize(latestThesis?.regime)}</Pill>
            </div>
            <p className="long-text">{latestThesis?.thesis ?? "Brak danych."}</p>
          </Panel>

          <Panel title="Kontrteza">
            <p className="long-text">
              {latestThesis?.anti_thesis ?? "Brak danych."}
            </p>
            <MetaRow label="Model" value={latestThesis?.model_name ?? "—"} />
          </Panel>
        </div>
      </Section>

      <Section
        title="Prognoza 1d / 5d / 20d"
        subtitle="Bieżące prognozy i historia poprzednich prognoz."
      >
        <div className="grid-3">
          {latestForecasts.map((forecast) => (
            <Panel
              key={`${forecast.horizon}-${forecast.generated_at}`}
              title={forecast.horizon}
            >
              <div className="pill-row">
                <Pill
                  tone={
                    forecast.direction === "up"
                      ? "good"
                      : forecast.direction === "down"
                      ? "bad"
                      : "warn"
                  }
                >
                  {forecast.direction}
                </Pill>
                <Pill>{titleize(forecast.regime_label)}</Pill>
              </div>
              <MetaRow
                label="Prawdopod. wzrostu"
                value={formatPct(forecast.up_probability)}
              />
              <MetaRow
                label="Prawdopod. spadku"
                value={formatPct(forecast.down_probability)}
              />
              <MetaRow label="Pewność" value={formatPct(forecast.confidence)} />
            </Panel>
          ))}
        </div>

        <div className="spacer" />
        <ForecastHistoryChart rows={forecastHistory} />
      </Section>

      <Section
        title="Wyniki tez"
        subtitle="Porównanie tez z faktycznym zachowaniem ceny."
      >
        <div className="grid-2">
          <OutcomesChart rows={thesisOutcomes} />
          <Panel title="Podsumowanie wyników">
            <MetaRow
              label="Łączna liczba wyników"
              value={String(thesisQualitySummary?.total_outcomes ?? 0)}
            />
            <MetaRow
              label="Śr. zrealizowany zwrot"
              value={
                thesisQualitySummary
                  ? formatPct(thesisQualitySummary.average_realized_return_pct, 3)
                  : "—"
              }
            />
          </Panel>
        </div>

        <div className="spacer" />

        <DataTable
          columns={["Horyzont","Cena bazowa","Cena zrealizowana","Zwrot %","Trafny kierunek","Wynik"]}
          rows={thesisOutcomes.slice(0, 12).map((r) => ({
            "Horyzont": r.horizon,
            "Cena bazowa": r.base_price?.toFixed(2) ?? "—",
            "Cena zrealizowana": r.realized_price?.toFixed(2) ?? "—",
            "Zwrot %": formatPct(r.realized_return_pct),
            "Trafny kierunek": r.was_directionally_correct ? "✓" : "✗",
            "Wynik": r.outcome_label,
          }))}
        />
      </Section>

      <Section
        title="Podsumowanie jakości"
        subtitle="Metryki jakości tez i prognoz na przestrzeni czasu."
      >
        <div className="grid-2">
          <ThesisQualityChart rows={thesisQualityByHorizon} />
          <Panel title="Jakość prognoz">
            {forecastQualitySummary.map((item) => (
              <div key={item.horizon} className="quality-block">
                <strong>{item.horizon}</strong>
                <MetaRow
                  label="Śr. prawdopod. wzrostu"
                  value={formatPct(item.average_up_probability)}
                />
                <MetaRow
                  label="Śr. pewność"
                  value={formatPct(item.average_confidence)}
                />
              </div>
            ))}
          </Panel>
        </div>
      </Section>

      <Section
        title="Historia narracji"
        subtitle="Ewolucja dominujących narracji rynkowych."
      >
        <NarrativeHistoryChart rows={narrativeHistory} />
      </Section>

    </PageContainer>
  );}