import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  Bell,
  Brain,
  Gauge,
  ShieldAlert,
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
import { adminHeaders, api, setApiBaseUrl } from "./lib/api";
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
  StoredThesis,
  StrategyComparison,
  ThesisOutcome,
  ThesisQualityByHorizon,
  ThesisQualitySummary,
  WalkForwardBacktest,
  Watchlist,
  MLModelComparison,
  MLMonitor,
  EarningsCalendarResponse,
  EarningsRecord,
  EarningsCallAnalysis,
  DynamicWeightInfo,
  InsiderTrade,
  ShortInterest,
  TopPick,
  RecommendationJournalRecord,
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

const Portfolio = lazy(() => import("./components/Portfolio").then(module => ({ default: module.Portfolio })));
const IntradayTab = lazy(() => import("./components/IntradayTab").then(module => ({ default: module.IntradayTab })));
const SimulatorTab = lazy(() => import("./components/SimulatorTab").then(module => ({ default: module.SimulatorTab })));
const AlertsConfigTab = lazy(() => import("./components/AlertsConfigTab").then(module => ({ default: module.AlertsConfigTab })));
const PaperTradingTab = lazy(() => import("./components/PaperTradingTab").then(module => ({ default: module.PaperTradingTab })));
const CalibrationAuditTab = lazy(() => import("./components/CalibrationAuditTab").then(module => ({ default: module.CalibrationAuditTab })));

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
  { value: "target_triple_barrier", label: "Triple barrier", description: "Czy pierwsza zostanie osiągnięta bariera zysku czy straty?" },
  { value: "target_meta_label", label: "Meta: trade/skip", description: "Czy sygnał bazowy ma przewagę po kosztach?" },
] as const;

const SELECTED_ASSET_STORAGE_KEY = "mstock-selected-asset";

function initialSelectedAsset() {
  try {
    return window.localStorage.getItem(SELECTED_ASSET_STORAGE_KEY) || "nvda";
  } catch {
    return "nvda";
  }
}

function mlPositive(label: string | null | undefined) {
  return ["up", "upper", "trade"].includes(label?.toLowerCase() ?? "");
}

function mlVerdict(target: string, positive: boolean) {
  if (target === "target_meta_label") return positive ? "TRADE" : "SKIP";
  if (target === "target_triple_barrier") return positive ? "GÓRNA BARIERA" : "DOLNA BARIERA";
  if (target === "target_thesis_success") return positive ? "TEZA TRAFNA" : "TEZA NIETRAFNA";
  return positive ? "WZROST" : "SPADEK";
}

function mlProbabilityName(target: string) {
  if (target === "target_meta_label") return "p(trade)";
  if (target === "target_triple_barrier") return "p(górna bariera)";
  if (target === "target_thesis_success") return "p(sukces)";
  return "p(wzrost)";
}

export default function App() {
  const [apiBase, setApiBase] = useState(api.apiBase);
  const updateApiBase = (url: string) => { setApiBase(url); setApiBaseUrl(url); };
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAsset, setSelectedAsset] = useState(initialSelectedAsset);
  const [activeTab, setActiveTab] = useState<"analysis" | "recommendations" | "calibration" | "quality" | "theses" | "portfolio" | "earnings" | "insider" | "toppicks" | "intraday" | "simulator" | "paper" | "alerts-config">("analysis");
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
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [events, setEvents] = useState<NotificationEvent[]>([]);

  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null);
  const [mlPrediction, setMlPrediction] = useState<MLPrediction | null>(null);
  const [mlPredictions, setMlPredictions] = useState<Record<string, MLPrediction | null>>({});
  const [mlModelsState, setMlModelsState] = useState<MLModelRun[]>([]);
  const [mlBacktestsState, setMlBacktestsState] = useState<MLBacktest[]>([]);
  const [mlDatasetStats, setMlDatasetStats] = useState<MLDatasetStats | null>(
    null
  );
  const [mlExplanation, setMlExplanation] = useState<MLExplanation | null>(null);
  const [mlComparison, setMlComparison] = useState<MLModelComparison[]>([]);
  const [mlMonitoring, setMlMonitoring] = useState<MLMonitor[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [recommendations, setRecommendations] = useState<AssetRecommendation[]>([]);
  const [selectedRecommendationJournal, setSelectedRecommendationJournal] = useState<RecommendationJournalRecord[]>([]);
  const [dataQuality, setDataQuality] = useState<DataQualityReport | null>(null);
  const [enrichingAsset, setEnrichingAsset] = useState<string | null>(null);
  const [enrichAllBusy, setEnrichAllBusy] = useState(false);
  const [priceHistory, setPriceHistory] = useState<PriceBar[]>([]);
  const [ensembleSignal, setEnsembleSignal] = useState<EnsembleSignal | null>(null);
  const [ensembleLeaderboard, setEnsembleLeaderboard] = useState<EnsembleLeaderboard[]>([]);
  const [ensembleDynWeights, setEnsembleDynWeights] = useState<DynamicWeightInfo | null>(null);
  const [earningsCalendar, setEarningsCalendar] = useState<EarningsCalendarResponse>({ upcoming: [], recent: [] });
  const [assetEarnings, setAssetEarnings] = useState<EarningsRecord[]>([]);
  const [earningsAnalyses, setEarningsAnalyses] = useState<EarningsCallAnalysis[]>([]);
  const [llmAnalyzeLoading, setLlmAnalyzeLoading] = useState(false);
  const [insiderTrades, setInsiderTrades] = useState<InsiderTrade[]>([]);
  const [shortInterest, setShortInterest] = useState<ShortInterest[]>([]);
  const [syncingInsider, setSyncingInsider] = useState(false);
  const [portfolioPositions, setPortfolioPositions] = useState<{
    asset_id: string;
    quantity: number;
    avg_buy_price: number | null;
    purchase_date: string | null;
    invested_amount: number | null;
  }[]>([]);
  const [topPicks, setTopPicks] = useState<TopPick[]>([]);
  const [ensembleMode, setEnsembleMode] = useState<string>("ensemble_weighted");
  const [showAddAsset, setShowAddAsset] = useState(false);
  const [newAsset, setNewAsset] = useState<AssetCreate>({
    id: "", symbol: "", name: "", type: "stock",
    sector: "", price_symbol: "", news_symbol: "", news_term: "", metal_price_fn: "",
  });
  const [mlActiveTarget, setMlActiveTarget] = useState<string>("target_up_5d");
  const [useOptuna, setUseOptuna] = useState<boolean>(false);
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

  useEffect(() => {
    if (!selectedAsset) return;
    try {
      window.localStorage.setItem(SELECTED_ASSET_STORAGE_KEY, selectedAsset);
    } catch {
      // Aplikacja pozostaje używalna również przy zablokowanym localStorage.
    }
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
      const res = await fetch(`${apiBase}/admin/run-pipeline`, { method: "POST", headers: adminHeaders() });
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

    // Lista aktywów używa rekomendacji do ikon stanu/prognozy. Ładuj ją
    // niezależnie od cięższych paneli ML, aby symbole pojawiały się od razu.
    void api.recommendations()
      .then(setRecommendations)
      .catch(() => {});
    void api.recommendationJournal(100, selectedAsset)
      .then(setSelectedRecommendationJournal)
      .catch(() => setSelectedRecommendationJournal([]));
    void api.mlMonitoring().then(setMlMonitoring).catch(() => {});

    try {
      // ── Faza 1: dane kluczowe — renderuje UI jak najszybciej ─────────────────
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
        currentMlStatus,
        currentMlPredictions,
        currentPriceHistory,
        currentEnsembleSignal,
        notificationChannels,
        currentPortfolioPositions,
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
        api.mlStatus().catch(() => null),
        Promise.all(
          ML_TARGETS.map(async target => [
            target.value,
            await api.latestMlPrediction(selectedAsset, target.value).catch(() => null),
          ] as const)
        ).then(entries => Object.fromEntries(entries) as Record<string, MLPrediction | null>),
        api.priceHistory(selectedAsset, 365).catch(() => []),
        api.ensembleSignal(selectedAsset, ensembleMode).catch(() => null),
        api.notificationChannels().catch(() => []),
        api.portfolioPositions().catch(() => []),
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
      setMlStatus(currentMlStatus);
      setMlPredictions(currentMlPredictions);
      setMlPrediction(currentMlPredictions[mlActiveTarget] ?? null);
      setPriceHistory(currentPriceHistory);
      setEnsembleSignal(currentEnsembleSignal);
      setChannels(notificationChannels);
      setPortfolioPositions(currentPortfolioPositions);
      setLastRefreshedAt(new Date());
      setLoading(false);  // odblokuj UI — faza 2 idzie w tle

      // ── Faza 2: dane pomocnicze — ładuje się po wyrenderowaniu UI ──────────
      const [
        notificationEvents,
        currentMlModels,
        currentMlBacktests,
        currentMlDatasetStats,
        currentMlComparison,
        currentAvailableModels,
        currentStrategyComparison,
        currentAllComparisons,
        currentDataQuality,
        currentEnsembleLeaderboard,
        currentEarningsCalendar,
        currentAssetEarnings,
        currentEarningsAnalyses,
        currentEnsembleDynWeights,
        currentInsiderTrades,
        currentShortInterest,
        currentTopPicks,
        currentMlExplanation,
      ] = await Promise.all([
        api.notificationEvents().catch(() => []),
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
        api.dataQuality().catch(() => null),
        api.ensembleLeaderboard().catch(() => []),
        api.earningsCalendar().catch(() => ({ upcoming: [], recent: [] })),
        api.assetEarnings(selectedAsset).catch(() => []),
        api.earningsAnalyses(selectedAsset).catch(() => []),
        api.ensembleWeights(selectedAsset).catch(() => null),
        api.insiderTrades(selectedAsset).catch(() => []),
        api.shortInterest(selectedAsset).catch(() => []),
        api.topPicks().catch(() => []),
        api.mlExplain(selectedAsset, mlActiveTarget).catch(() => null),
      ]);

      setEvents(notificationEvents);
      setMlModelsState(currentMlModels);
      setMlBacktestsState(currentMlBacktests);
      setMlDatasetStats(currentMlDatasetStats);
      setMlComparison(currentMlComparison);
      setAvailableModels(currentAvailableModels?.available ?? []);
      setStrategyComparison(currentStrategyComparison);
      setAllComparisons(currentAllComparisons);
      setDataQuality(currentDataQuality);
      setEnsembleLeaderboard(currentEnsembleLeaderboard);
      setEarningsCalendar(currentEarningsCalendar);
      setAssetEarnings(currentAssetEarnings);
      setEarningsAnalyses(currentEarningsAnalyses);
      setEnsembleDynWeights(currentEnsembleDynWeights);
      setInsiderTrades(currentInsiderTrades);
      setShortInterest(currentShortInterest);
      setTopPicks(currentTopPicks);
      setMlExplanation(currentMlExplanation);
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
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
      const removeEmergencyBlock = mlStatus?.emergency_disabled ?? false;
      const result = await api.setMlMode(removeEmergencyBlock);
      setInfo(
        result.emergency_disabled
          ? "Włączono awaryjną blokadę ML. Modele nadal pracują w shadow."
          : "Wyłączono awaryjną blokadę. Aktywacja modeli pozostaje automatyczna."
      );
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
        await api.trainMlModel(mlActiveTarget, modelName, selectedAsset, useOptuna);
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

  async function runMlMonitoringNow() {
    setMlWorking("Monitoring driftu i wyników modeli…");
    try {
      const rows = await api.runMlMonitoring();
      setMlMonitoring(rows);
      const degraded = rows.filter(row => row.is_degraded).length;
      const rollbacks = rows.filter(row => row.action === "rollback").length;
      setInfo(`Monitoring: ${rows.length} modeli, degradacja ${degraded}, rollback ${rollbacks}.`);
      await refresh();
    } catch (err) {
      setError(humanizeError(err instanceof Error ? err.message : String(err)));
    } finally {
      setMlWorking(null);
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
    setMlPredictions({});
    setMlPrediction(null);
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
      setMlPredictions(current => ({ ...current, [mlActiveTarget]: pred }));
      setMlExplanation(expl);
    });
  }, [mlActiveTarget]);

  // Auto-refresh UI dopiero po zakończeniu cyklu. Zmiana next_run zachodziła
  // na początku zadania, więc poprzednia wersja pobierała jeszcze stary status ML.
  useEffect(() => {
    let wasRunning = false;
    let initialized = false;

    const id = setInterval(async () => {
      try {
        const r = await fetch(`${apiBase}/admin/sync-status`);
        const d = await r.json();
        const running = Boolean(d?.running);
        if (!initialized) {
          wasRunning = running;
          initialized = true;
          return;
        }
        if (wasRunning && !running) {
          void refresh();
        }
        wasRunning = running;
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
        recommendations={recommendations}
      />

      {/* ── Zakładki ─────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: "0.25rem", margin: "0.6rem 0 0.2rem", borderBottom: "2px solid var(--border)" }}>
        {([["analysis", "Analizy"], ["recommendations", "Rekomendacje"], ["calibration", "Kalibracja"], ["toppicks", "⭐ Top Picks"], ["intraday", "📈 Intraday"], ["simulator", "📊 Symulator"], ["paper", "🧾 Paper trading"], ["quality", "Jakość danych"], ["theses", "Tezy"], ["earnings", "Wyniki spółek"], ["insider", "Insider & Short"], ["portfolio", "Portfel"], ["alerts-config", "🔔 Alerty SMS"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            style={{
              padding: "6px 20px", border: "none", background: "none", cursor: "pointer",
              fontSize: "0.88rem", fontWeight: activeTab === id ? 700 : 400,
              color: activeTab === id ? "var(--accent)" : "var(--text-3)",
              borderBottom: activeTab === id ? "2px solid var(--accent)" : "2px solid transparent",
              marginBottom: -2, borderRadius: "4px 4px 0 0", transition: "color 0.15s",
            }}
          >{id === "toppicks" ? `⭐ Top Picks (${topPicks.length})` : label}</button>
        ))}
      </div>

      <Suspense fallback={
        <Section title="Ładowanie modułu">
          <p style={{ color: "var(--text-2)" }}>Trwa przygotowywanie wybranego widoku…</p>
        </Section>
      }>

      {/* ── Zakładka Tezy ────────────────────────────────────────────────── */}
      {activeTab === "theses" && <>
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
            <p className="long-text">{latestThesis?.anti_thesis ?? "Brak danych."}</p>
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
            <Panel key={`${forecast.horizon}-${forecast.generated_at}`} title={forecast.horizon}>
              <div className="pill-row">
                <Pill tone={forecast.direction === "up" ? "good" : forecast.direction === "down" ? "bad" : "warn"}>
                  {forecast.direction}
                </Pill>
                <Pill>{titleize(forecast.regime_label)}</Pill>
              </div>
              <MetaRow label="Prawdopod. wzrostu" value={formatPct(forecast.up_probability)} />
              <MetaRow label="Prawdopod. spadku"  value={formatPct(forecast.down_probability)} />
              <MetaRow label="Pewność"             value={formatPct(forecast.confidence)} />
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
            <MetaRow label="Łączna liczba wyników" value={String(thesisQualitySummary?.total_outcomes ?? 0)} />
            <MetaRow
              label="Śr. zrealizowany zwrot"
              value={thesisQualitySummary ? formatPct(thesisQualitySummary.average_realized_return_pct, 3) : "—"}
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
                <MetaRow label="Śr. prawdopod. wzrostu" value={formatPct(item.average_up_probability)} />
                <MetaRow label="Śr. pewność"             value={formatPct(item.average_confidence)} />
              </div>
            ))}
          </Panel>
        </div>
      </Section>
      </> /* koniec zakładki Tezy */}

      {/* ── Zakładka Portfel ─────────────────────────────────────────────── */}
      {activeTab === "portfolio" && (
        <Portfolio apiBase={apiBase} assets={assets} />
      )}

      {/* ── Zakładka Analizy (cała istniejąca treść) ─────────────────────── */}
      {activeTab === "analysis" && <>

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
          {mlStatus?.emergency_disabled ? "Odblokuj automat ML" : "Awaryjnie wyłącz ML"}
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
        <button className="secondary-button" onClick={runMlMonitoringNow} disabled={!!mlWorking}>
          <ShieldAlert size={16} />
          Monitoruj drift
        </button>
        <label
          data-tip="Optuna przeszuka przestrzeń hiperparametrów (30 prób, 3-fold CV jako cel) i wybierze najlepsze C, max_depth, learning_rate itp. przed treningiem finalnym. Trwa dłużej (~1-3 min per model)."
          data-tip-side="bottom"
          style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", cursor: "pointer",
            padding: "6px 12px", border: "1px solid var(--border-2)", borderRadius: "10px",
            background: useOptuna ? "rgba(139,92,246,0.10)" : "var(--bg-card)",
            color: useOptuna ? "#7c3aed" : "var(--text-2)",
            fontSize: "13px", fontWeight: useOptuna ? 600 : 400,
            borderColor: useOptuna ? "#7c3aed" : "var(--border-2)",
            transition: "all 0.15s", userSelect: "none" }}
        >
          <input type="checkbox" checked={useOptuna} onChange={e => setUseOptuna(e.target.checked)}
            style={{ accentColor: "#7c3aed", width: 14, height: 14 }} />
          Optuna auto-tuning
        </label>
      </div>

      {/* Rząd 2 — pozostałe akcje */}
      <div className="toolbar-row" style={{ marginTop: "0.4rem" }}>
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

      {/* ── Panel "Co zrobić z tą pozycją?" ── */}
      {(() => {
        const rec = recommendations.find(r => r.asset_id === selectedAsset);
        if (!rec) return null;

        const myPos = portfolioPositions.find(p => p.asset_id === selectedAsset && p.quantity > 0) ?? null;
        const isOwned = myPos !== null;

        // ── Oblicz akcję ─────────────────────────────────────────────────────
        const conviction = rec.conviction_score ?? 50;
        const riskScore  = rec.risk_score ?? 50;
        const reco       = rec.recommendation;
        const ensDir     = ensembleSignal?.final_direction ?? null;
        const ensConf    = ensembleSignal?.final_confidence ?? 0;
        const lastActionableSignal = reco === "KUP" || reco === "SPRZEDAJ"
          ? null
          : selectedRecommendationJournal.find(row =>
              row.data_complete && (row.displayed_action === "KUP" || row.displayed_action === "SPRZEDAJ")
            ) ?? null;
        const lastSignalBullet = lastActionableSignal
          ? `Ostatni zapisany sygnał: ${lastActionableSignal.displayed_action} — ${new Date(lastActionableSignal.created_at).toLocaleString("pl-PL")} (obecnie nieaktywny)`
          : "";

        type ActionLevel = "strong_buy" | "buy" | "hold" | "reduce" | "exit" | "watch" | "skip";
        let action: ActionLevel;
        let actionLabel: string;
        let actionColor: string;
        let actionBg: string;
        let headline: string;
        let bullets: string[];

        if (isOwned) {
          // ── Tryb: posiadacz ────────────────────────────────────────────────
          if (reco === "SPRZEDAJ" && conviction > 60) {
            action = "exit"; actionLabel = "WYJDŹ Z POZYCJI";
            actionColor = "#dc2626"; actionBg = "rgba(220,38,38,0.08)";
            headline = "Sygnały wskazują na wyjście — rozważ sprzedaż";
          } else if (reco === "SPRZEDAJ" || (reco === "TRZYMAJ" && riskScore > 65)) {
            action = "reduce"; actionLabel = "ROZWAŻ REDUKCJĘ";
            actionColor = "#f59e0b"; actionBg = "rgba(245,158,11,0.08)";
            headline = "Podwyższone ryzyko — możliwa częściowa realizacja zysku";
          } else if (reco === "KUP" && conviction > 65 && riskScore < 50) {
            action = "strong_buy"; actionLabel = "ZWIĘKSZ POZYCJĘ";
            actionColor = "#16a34a"; actionBg = "rgba(22,163,74,0.09)";
            headline = "Silny sygnał — warunki sprzyjają doważeniu";
          } else if (reco === "KUP") {
            action = "buy"; actionLabel = "TRZYMAJ / ROZWAŻ DOWAŻENIE";
            actionColor = "#22c55e"; actionBg = "rgba(34,197,94,0.08)";
            headline = "Sygnał bycze — trzymaj i obserwuj";
          } else {
            action = "hold"; actionLabel = "TRZYMAJ";
            actionColor = "#6366f1"; actionBg = "rgba(99,102,241,0.07)";
            headline = "Brak silnego sygnału — trzymaj obecną pozycję";
          }
          bullets = [
            myPos.avg_buy_price != null
              ? `Twoja pozycja: ${myPos.quantity} szt. śr. po ${myPos.avg_buy_price.toFixed(2)} ${selectedMeta?.currency ?? ""}`
              : `Twoja pozycja: ${myPos.quantity} szt.`,
            `Rekomendacja systemu: ${reco} (historyczne P=${rec.confidence.toFixed(1)}%, próba n=${rec.calibration_sample_size})`,
            lastSignalBullet,
            `Przewaga netto: ${rec.expected_net_edge_pct.toFixed(2)}% ± ${rec.uncertainty_pct.toFixed(2)}%, koszt: ${rec.transaction_cost_pct.toFixed(2)}%`,
            ensDir ? `Sygnał ensemble: ${ensDir === "up" ? "▲ wzrostowy" : "▼ spadkowy"} (pewność ${(ensConf).toFixed(0)}%)` : "",
            rec.forecast_dir_5d ? `Prognoza 5d: ${rec.forecast_dir_5d === "up" ? "▲ wzrost" : "▼ spadek"}` : "",
            rec.forecast_dir_20d ? `Prognoza 20d: ${rec.forecast_dir_20d === "up" ? "▲ wzrost" : "▼ spadek"}` : "",
          ].filter(Boolean);
        } else {
          // ── Tryb: obserwujący ─────────────────────────────────────────────
          if (reco === "KUP" && conviction > 65 && riskScore < 45) {
            action = "strong_buy"; actionLabel = "ROZWAŻ OTWARCIE POZYCJI";
            actionColor = "#16a34a"; actionBg = "rgba(22,163,74,0.09)";
            headline = "Silny sygnał wejścia — spójne potwierdzenie wielu wskaźników";
          } else if (reco === "KUP") {
            action = "buy"; actionLabel = "WEJŚCIE WARUNKOWE";
            actionColor = "#22c55e"; actionBg = "rgba(34,197,94,0.08)";
            headline = "Sygnał kupna, ale czekaj na dalsze potwierdzenie";
          } else if (reco === "BRAK TRANSAKCJI") {
            action = "watch"; actionLabel = "BRAK TRANSAKCJI";
            actionColor = "#64748b"; actionBg = "rgba(100,116,139,0.08)";
            headline = "Przewaga nie pokrywa kosztów i niepewności — pozostań poza rynkiem";
          } else if (reco === "TRZYMAJ") {
            action = "watch"; actionLabel = "OBSERWUJ";
            actionColor = "#6366f1"; actionBg = "rgba(99,102,241,0.07)";
            headline = "Sygnał neutralny — nie otwieraj pozycji bez wyraźnego katalizatora";
          } else {
            action = "skip"; actionLabel = "POMIŃ";
            actionColor = "#ef4444"; actionBg = "rgba(239,68,68,0.07)";
            headline = "Sygnał negatywny — nie otwieraj pozycji";
          }
          bullets = [
            `Aktywo: ${selectedMeta?.symbol} — ${selectedMeta?.name ?? ""}`,
            `Rekomendacja: ${reco} (historyczne P=${rec.confidence.toFixed(1)}%, próba n=${rec.calibration_sample_size})`,
            lastSignalBullet,
            `Przewaga netto: ${rec.expected_net_edge_pct.toFixed(2)}% ± ${rec.uncertainty_pct.toFixed(2)}%, koszt: ${rec.transaction_cost_pct.toFixed(2)}%`,
            ensDir ? `Sygnał ensemble: ${ensDir === "up" ? "▲ wzrostowy" : "▼ spadkowy"} (pewność ${(ensConf).toFixed(0)}%)` : "",
            rec.forecast_dir_5d ? `Prognoza 5d: ${rec.forecast_dir_5d === "up" ? "▲ wzrost" : "▼ spadek"}` : "",
            rec.forecast_dir_20d ? `Prognoza 20d: ${rec.forecast_dir_20d === "up" ? "▲ wzrost" : "▼ spadek"}` : "",
          ].filter(Boolean);
        }

        // Kluczowe sygnały z top_signals (max 3)
        const topSigs = (rec.top_signals ?? []).slice(0, 3);

        // Warunki unieważnienia z tezy (max 2)
        const invalidations = latestThesis?.invalidation_conditions?.slice(0, 2) ?? [];

        return (
          <div style={{
            margin: "0 0 20px", padding: "1rem 1.2rem",
            borderRadius: "10px", border: `1.5px solid ${actionColor}40`,
            background: actionBg, position: "relative",
          }}>
            {/* Nagłówek */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
              <span style={{
                padding: "3px 12px", borderRadius: "6px", fontWeight: 700, fontSize: "0.8rem",
                letterSpacing: "0.06em", background: `${actionColor}18`, color: actionColor,
              }}>{actionLabel}</span>
              <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text)" }}>{headline}</span>
              <span style={{
                marginLeft: "auto", fontSize: "0.7rem", color: "var(--text-3)",
                padding: "2px 8px", borderRadius: "4px", background: "var(--surface)",
              }}>{isOwned ? "📂 Mam tę pozycję" : "👁 Obserwuję"}</span>
            </div>

            {/* Sygnały */}
            <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", marginBottom: topSigs.length || invalidations.length ? "0.75rem" : 0 }}>
              <div>
                <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.3rem" }}>Kontekst</div>
                <ul style={{ margin: 0, padding: "0 0 0 1rem", listStyle: "disc", fontSize: "0.8rem", color: "var(--text)", lineHeight: 1.7 }}>
                  {bullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>

              {topSigs.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.3rem" }}>Kluczowe sygnały</div>
                  <ul style={{ margin: 0, padding: "0 0 0 1rem", listStyle: "none", fontSize: "0.8rem", lineHeight: 1.7 }}>
                    {topSigs.map((s, i) => (
                      <li key={i} style={{ color: s.direction === "bullish" ? "#16a34a" : s.direction === "bearish" ? "#dc2626" : "var(--text-2)" }}>
                        {s.direction === "bullish" ? "▲" : s.direction === "bearish" ? "▼" : "●"} {s.name}
                        <span style={{ color: "var(--text-3)", fontSize: "0.72rem", marginLeft: "0.4rem" }}>
                          ({s.normalized > 0 ? "+" : ""}{(s.normalized * 100).toFixed(0)}%)
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {invalidations.length > 0 && (
                <div>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.3rem" }}>Kiedy zmienić zdanie</div>
                  <ul style={{ margin: 0, padding: "0 0 0 1rem", listStyle: "disc", fontSize: "0.78rem", color: "var(--text-2)", lineHeight: 1.7 }}>
                    {invalidations.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
            </div>

            {/* Stopka z rationale */}
            {rec.rationale && (
              <div style={{ fontSize: "0.75rem", color: "var(--text-2)", borderTop: "1px solid var(--border)", paddingTop: "0.5rem", lineHeight: 1.5 }}>
                <strong>Uzasadnienie: </strong>{rec.rationale}
              </div>
            )}
          </div>
        );
      })()}

      {/* ── Historia ceny ── */}
      {selectedMeta && (
        <div style={{ marginBottom: "24px" }}>

          {/* ── Pasek sygnałów ── */}
          {(() => {
            const rec    = recommendations.find(r => r.asset_id === selectedAsset) ?? null;
            const recKey = rec?.recommendation === "KUP" ? "buy" : rec?.recommendation === "SPRZEDAJ" ? "sell" : "hold";
            const ensAct = ensembleSignal?.action ?? null;
            const ensKey = ensAct === "KUP" ? "buy" : ensAct === "SPRZEDAJ" ? "sell" : "hold";

            const colors: Record<string, { bg: string; border: string; text: string }> = {
              buy:  { bg: "rgba(22,163,74,0.11)",  border: "rgba(22,163,74,0.38)",  text: "#16a34a" },
              sell: { bg: "rgba(220,38,38,0.10)",  border: "rgba(220,38,38,0.38)",  text: "#dc2626" },
              hold: { bg: "var(--bg-card)",         border: "var(--border)",          text: "var(--text-2)" },
            };

            function SignalBox({ colorKey, title, verdict, detail, tooltip }: {
              colorKey: string; title: string; verdict: string; detail: string; tooltip: string;
            }) {
              const c = colors[colorKey] ?? colors.hold;
              return (
                <div title={tooltip} style={{
                  borderRadius: "8px", padding: "9px 14px",
                  background: c.bg, border: `1.5px solid ${c.border}`,
                  cursor: "default", minWidth: 170,
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
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(7, minmax(170px, 1fr))",
                gap: "10px",
                marginBottom: "10px",
                overflowX: "auto",
                paddingBottom: "3px",
              }}>
                <SignalBox
                  colorKey={recKey}
                  title="Rekomendacja"
                  verdict={rec?.recommendation ?? "—"}
                  detail={rec ? `score ${rec.composite_score} · pewność: ${rec.confidence_label}` : "brak danych"}
                  tooltip={rec?.rationale ?? "Brak danych rekomendacji"}
                />
                {ML_TARGETS.map(target => {
                  const prediction = mlPredictions[target.value] ?? null;
                  const positive = prediction ? mlPositive(prediction.predicted_label) : false;
                  const colorKey = !prediction
                    ? "hold"
                    : target.value === "target_meta_label" && !positive
                      ? "hold"
                      : positive ? "buy" : "sell";
                  const probabilityName = mlProbabilityName(target.value);
                  return (
                    <SignalBox
                      key={target.value}
                      colorKey={colorKey}
                      title={`ML · ${target.label}`}
                      verdict={prediction ? mlVerdict(target.value, positive) : "—"}
                      detail={prediction
                        ? `${probabilityName} = ${(prediction.probability_up * 100).toFixed(1)}%`
                        : "brak predykcji"}
                      tooltip={prediction
                        ? `Cel: ${prediction.target_name} | ${probabilityName} = ${(prediction.probability_up * 100).toFixed(1)}%`
                        : `Brak predykcji ML dla celu: ${target.label}`}
                    />
                  );
                })}
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
        subtitle="Modele kierunku, skuteczności tezy, triple barrier i meta-labelingu."
      >
        {/* ── Selektor celu dla narzędzi i widoku szczegółowego ── */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.82rem", color: "var(--text-2)", fontWeight: 500 }}>Cel szczegółów i narzędzi:</span>
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
                  ? <span style={{ color: t.activation_state === "eligible" ? "#16a34a" : t.activation_state === "degraded" ? "#dc2626" : "#d97706" }}>
                      {t.activation_state === "eligible" ? "✓ Live" : t.activation_state === "degraded" ? "⚠ Degradacja" : t.activation_state === "partial" ? "◐ Częściowo live" : "◌ Shadow"} — {t.model_name}
                    </span>
                  : <span style={{ color: "var(--text-3)" }}>Brak modelu</span>}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-2)", marginTop: "0.15rem" }}>
                {t.dataset_rows} wierszy · live {t.eligible_models}/{t.active_models}
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
          <span title="Tryb jest wyznaczany automatycznie osobno dla każdego modelu">
            <span style={{ color: "var(--text-2)" }}>tryb </span>
            <strong style={{ color: mlStatus?.ml_enabled ? "#16a34a" : "var(--text)" }}>{mlStatus?.ml_mode ?? "—"}</strong>
          </span>
          <span title="Modele dopuszczone do rekomendacji / wszystkie aktywne championy">
            <span style={{ color: "var(--text-2)" }}>live </span>
            <strong>{mlStatus?.eligible_models ?? 0}/{mlStatus?.active_models ?? 0}</strong>
            <span style={{ color: "var(--text-3)" }}> · shadow {mlStatus?.shadow_models ?? 0} · degraded {mlStatus?.degraded_models ?? 0}</span>
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
            {" · "}
            <span title="target_triple_barrier">3B: <strong>{mlDatasetStats?.triple_barrier_rows ?? 0}</strong></span>
            {" · "}
            <span title="target_meta_label">meta: <strong>{mlDatasetStats?.meta_label_rows ?? 0}</strong></span>
            <span title="Meta-label wygenerowany przez primary model out-of-fold">OOF: <strong>{mlDatasetStats?.oof_meta_label_rows ?? 0}</strong></span>
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
                  background: mlPositive(mlExplanation.predicted_label) ? "rgba(22,163,74,0.08)" : "rgba(220,38,38,0.08)",
                  border: `1.5px solid ${mlPositive(mlExplanation.predicted_label) ? "#16a34a" : "#dc2626"}`,
                }}>
                  <span style={{ fontSize: "1.5rem", fontWeight: 700, color: mlPositive(mlExplanation.predicted_label) ? "#16a34a" : "#dc2626" }}>
                    {mlPositive(mlExplanation.predicted_label) ? "▲" : "▼"}
                  </span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem", color: mlPositive(mlExplanation.predicted_label) ? "#16a34a" : "#dc2626" }}>
                      {mlVerdict(mlActiveTarget, mlPositive(mlExplanation.predicted_label))}{" — "}{(mlExplanation.probability_up * 100).toFixed(1)}% {mlProbabilityName(mlActiveTarget)}
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
              const isUp = mlPositive(label);
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
                        {mlVerdict(mlActiveTarget, isUp)}{" — "}{(probUp * 100).toFixed(1)}% {mlProbabilityName(mlActiveTarget)}
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
              columns={["Aktywo","Cel","Model","Rola","Wierszy","Aktywny","Wytrenowano"]}
              rows={mlModelsState.map((row) => ({
                "Aktywo": row.asset_id
                  ? (assets.find(a => a.id === row.asset_id)?.name ?? row.asset_id)
                  : row.market_segment ? `Rynek ${row.market_segment}` : "Globalny",
                "Cel": row.target_name,
                "Model": row.model_name,
                "Rola": row.deployment_role,
                "Wierszy": String(row.dataset_rows),
                "Aktywny": row.is_active ? "✓" : "—",
                "Wytrenowano": new Date(row.trained_at).toLocaleDateString("pl-PL"),
              }))}
            />
          </Panel>

          <Panel title="Monitoring modeli">
            <DataTable
              maxRows={12}
              columns={["Zakres","PSI","Kalibracja","Zwrot netto","PF","N","Stan","Akcja"]}
              rows={mlMonitoring.map(row => ({
                "Zakres": row.asset_id ?? row.market_segment ?? "global",
                "PSI": row.feature_psi?.toFixed(3) ?? "—",
                "Kalibracja": row.calibration_error?.toFixed(3) ?? "—",
                "Zwrot netto": row.recent_avg_net_return_pct != null ? `${row.recent_avg_net_return_pct.toFixed(2)}%` : "—",
                "PF": row.recent_profit_factor?.toFixed(2) ?? "—",
                "N": String(row.sample_size),
                "Stan": row.is_degraded ? "⚠ degradacja" : "✓ stabilny",
                "Akcja": row.action,
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
          type PRow = { asset_id: string; maxRows: number; [k: string]: number | string | boolean | null };
          const pivotRows: PRow[] = Object.entries(byAsset).map(([assetId, models]) => {
            const row: PRow = { asset_id: assetId, maxRows: 0 };
            for (const mn of modelTypes) {
              const m = models[mn];
              const s = MODEL_SHORT[mn] ?? mn;
              row[`${s}_acc`]    = m ? m.accuracy : -1;
              row[`${s}_f1`]     = m ? m.f1       : -1;
              row[`${s}_cv_acc`] = m ? (m.cv_accuracy_mean ?? -1) : -1;
              row[`${s}_cv_f1`]  = m ? (m.cv_f1_mean       ?? -1) : -1;
              row[`${s}_cv_std`] = m ? (m.cv_f1_std        ?? null) : null;
              row[`${s}_optuna`] = m ? (m.optuna_best_params ? 1 : 0) : 0;
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

          const colGroups: { col: string; label: string; tooltip: string; isCV?: boolean }[] = [];
          for (const mn of modelTypes) {
            const s = MODEL_SHORT[mn] ?? mn;
            const long = MODEL_LONG[mn] ?? mn;
            colGroups.push({ col: `${s}_acc`,    label: `${s} Acc`,    tooltip: `${long}\n\nAccuracy na zbiorze testowym (20% danych). Jak często model ma rację.` });
            colGroups.push({ col: `${s}_f1`,     label: `${s} F1`,     tooltip: `${long}\n\nF1 na zbiorze testowym. Lepszy od Accuracy przy niezbalansowanych klasach.` });
            colGroups.push({ col: `${s}_cv_acc`, label: `${s} CV Acc`, tooltip: `${long}\n\nPurged temporal CV Accuracy — sesje są grupowane, a pomiędzy treningiem i testem pozostaje purge zależny od horyzontu.`, isCV: true });
            colGroups.push({ col: `${s}_cv_f1`,  label: `${s} CV F1`,  tooltip: `${long}\n\nPurged temporal CV F1 — bez losowego mieszania przyszłości z przeszłością. ±std dostępne po najechaniu.`, isCV: true });
          }

          return (
            <Panel title="Porównanie modeli">
              {filtered.length === 0 ? (
                <p className="long-text">Brak wytrenowanych modeli. Kliknij „Trenuj wszystkie modele" po zebraniu danych.</p>
              ) : (
                <div style={{ maxHeight: "22rem", overflowY: "auto", overflowX: "auto" }}>
                  {mlComparison.some(r => r.is_global) && (
                    <div style={{ fontSize: "0.72rem", color: "var(--text-3)", marginBottom: "0.3rem" }}>
                      * model rynku/globalny użyty, gdy brak bezpiecznego modelu per-aktywo
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
                          {colGroups.map(({ col, isCV }) => {
                            const v = row[col] as number;
                            const modelShort = col.replace(/_(acc|f1|cv_acc|cv_f1)$/, "");
                            const isGlobal = row[`${modelShort}_global`] as boolean;
                            const std = isCV && col.endsWith("_cv_f1") ? row[`${modelShort}_cv_std`] as number | null : null;
                            const hasOptuna = !!(row[`${modelShort}_optuna`]);
                            const cellTitle = [
                              isGlobal ? "Model globalny (nie per-aktywo)" : "",
                              std != null ? `±${(std * 100).toFixed(1)}% std` : "",
                              hasOptuna ? "Trenowany z Optuna auto-tuning" : "",
                            ].filter(Boolean).join(" · ") || undefined;
                            return (
                              <td key={col} style={{ ...tdStyle(v), opacity: isGlobal ? 0.65 : 1,
                                background: isCV ? "rgba(139,92,246,0.04)" : undefined }}
                                title={cellTitle}>
                                {v < 0 ? <span style={{ color: "var(--text-3)" }}>—</span> : (
                                  <span>
                                    {`${(v * 100).toFixed(1)}%`}
                                    {std != null && <span style={{ fontSize: "0.65rem", color: "var(--text-3)", marginLeft: 2 }}>±{(std * 100).toFixed(1)}</span>}
                                    {isGlobal && <span style={{ color: "var(--text-3)" }}>*</span>}
                                    {hasOptuna && isCV && <span title="Optuna" style={{ marginLeft: 3, fontSize: "0.6rem", color: "#7c3aed" }}>⚡</span>}
                                  </span>
                                )}
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
                      <div style={{ marginTop: "0.5rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.25rem" }}>
                          <span style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Wagi</span>
                          {ensembleSignal.weights_dynamic ? (
                            <span style={{ fontSize: "0.62rem", padding: "0.05rem 0.35rem", borderRadius: 4, background: "rgba(99,102,241,0.12)", color: "#6366f1", fontWeight: 600 }}>
                              dynamiczne · {ensembleSignal.weights_evaluated_records} ewaluacji
                            </span>
                          ) : (
                            <span style={{ fontSize: "0.62rem", padding: "0.05rem 0.35rem", borderRadius: 4, background: "var(--bg-subtle)", color: "var(--text-3)", fontWeight: 500 }}>
                              domyślne · za mało danych
                            </span>
                          )}
                        </div>
                        {/* pasek wag */}
                        <div style={{ display: "flex", height: "10px", borderRadius: 5, overflow: "hidden", gap: "1px" }}>
                          <div style={{ flex: ensembleSignal.heuristic_weight, background: "#4f86f7" }} title={`Heurystyka ${(ensembleSignal.heuristic_weight*100).toFixed(0)}%`} />
                          <div style={{ flex: ensembleSignal.ml_weight, background: "#22c55e" }} title={`ML ${(ensembleSignal.ml_weight*100).toFixed(0)}%`} />
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.67rem", marginTop: "0.15rem" }}>
                          <span style={{ color: "#4f86f7" }}>Heurystyka {(ensembleSignal.heuristic_weight*100).toFixed(0)}%{ensembleDynWeights?.is_dynamic ? ` · ${(ensembleDynWeights.heuristic_accuracy*100).toFixed(0)}% traf.` : ""}</span>
                          <span style={{ color: "#22c55e" }}>ML {(ensembleSignal.ml_weight*100).toFixed(0)}%{ensembleDynWeights?.is_dynamic ? ` · ${(ensembleDynWeights.ml_accuracy*100).toFixed(0)}% traf.` : ""}</span>
                        </div>
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
              Leaderboard — historyczna trafność predykcji
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.79rem" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)" }}>
                    {([
                      ["Aktywo", "Symbol i nazwa aktywa. Kliknij wiersz aby wybrać."],
                      ["Sygnałów", "Łączna liczba zapisanych sygnałów ensemble (ocenionych i oczekujących na outcome po 5 dniach)."],
                      ["Ocenionych", "Liczba sygnałów z wypełnionym wynikiem (outcome znany po ~5 dniach od zapisu). Reszta to sygnały zbyt świeże."],
                      ["Trafność H", "% sygnałów heurystycznych gdzie przewidziany kierunek (up/down) był zgodny z faktycznym ruchem ceny po 5 dniach. Pogrubiona = najwyższa trafność."],
                      ["Trafność ML", "% sygnałów ML gdzie przewidziany kierunek był zgodny z faktycznym ruchem ceny po 5 dniach. Pogrubiona = najwyższa trafność."],
                      ["Trafność Ens", "% sygnałów ensemble gdzie zbiorczy kierunek był zgodny z faktycznym ruchem ceny po 5 dniach. Pogrubiona = najwyższa trafność."],
                      ["Zalecany tryb", "Tryb z najwyższą historyczną trafnością dla tego aktywa. Używaj go w konfiguracji ensemble."],
                      ["Pewność H", "Średnia pewność sygnałów heurystycznych (0–100%). Wyższa = heurystyka bardziej przekonana do swoich sygnałów."],
                      ["Pewność ML", "Średnia pewność sygnałów ML (0–100%). Wyższa = modele ML bardziej przekonane do swoich predykcji."],
                    ] as [string, string][]).map(([label, tip]) => (
                      <th key={label} title={tip} style={{ padding: "0.3rem 0.5rem", textAlign: "left", fontWeight: 600, fontSize: "0.72rem", color: "var(--text-2)", whiteSpace: "nowrap", cursor: "help" }}>
                        {label} <span style={{ fontSize: "0.62rem", opacity: 0.55, fontWeight: 400 }}>?</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ensembleLeaderboard.map(row => {
                    const best = Math.max(row.heuristic_accuracy, row.ml_accuracy, row.ensemble_accuracy);
                    const modeColors: Record<string,string> = { heuristic:"#4f86f7", ml:"#22c55e", ensemble_weighted:"#f59e0b", ensemble_majority:"#a855f7" };
                    const modeLabels: Record<string,string> = { heuristic:"Heurystyka", ml:"ML", ensemble_weighted:"Ensemble ważony", ensemble_majority:"Ensemble większościowy" };
                    const accCell = (acc: number, key: string) => (
                      <td key={key} style={{ padding: "0.3rem 0.5rem", fontWeight: acc === best && acc > 0 ? 700 : 400,
                        color: acc === best && acc > 0 ? "#16a34a" : "inherit" }}>
                        {row.evaluated_records > 0 ? `${(acc * 100).toFixed(0)}%` : "—"}
                      </td>
                    );
                    return (
                      <tr key={row.asset_id} style={{ borderBottom: "1px solid var(--border)", background: row.asset_id === selectedAsset ? "var(--bg-hover)" : undefined, cursor: "pointer" }}
                        onClick={() => setSelectedAsset(row.asset_id)}>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: 600 }}>{row.name}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.total_records}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{row.evaluated_records}</td>
                        {accCell(row.heuristic_accuracy, "h")}
                        {accCell(row.ml_accuracy, "ml")}
                        {accCell(row.ensemble_accuracy, "ens")}
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
              Trafność wypełnia się po tym jak sygnały dostaną outcomes (po ~5 dniach od zapisania).
              Używaj "Ensemble ważony" dopóki leaderboard nie wskaże wyraźnego zwycięzcy.
            </p>
          </>
        )}
      </Section>

      </> /* koniec zakładki Analizy */}

      {/* ── Zakładka Rekomendacje ───────────────────────────────────────────── */}
      {activeTab === "recommendations" && <>
      <Section
        title="Tabela rekomendacji"
        subtitle="Decyzje KUP / SPRZEDAJ / TRZYMAJ / BRAK TRANSAKCJI skalibrowane historycznie osobno dla rynku i reżimu."
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
                    ["Rekomendacja","recommendation","Decyzja po odjęciu kosztów i uwzględnieniu niepewności. BRAK TRANSAKCJI oznacza, że żadna strona nie ma wystarczającej przewagi."],
                    ["Wynik","composite_score","Surowy wynik diagnostyczny dawnych sygnałów 0–100. Nie wyznacza już progów decyzji."],
                    ["Pewność","confidence","Historycznie skalibrowane prawdopodobieństwo trafności wybranej decyzji, liczone out-of-sample dla GPW/USA i bieżącego reżimu."],
                    ["Przewaga","expected_net_edge_pct","Oczekiwany zwrot kierunkowy po odjęciu kosztu transakcji. Transakcja wymaga przewagi większej od błędu statystycznego."],
                    ["Kalibracja","calibration_sample_size","Segment rynku, zakres kalibracji oraz liczba historycznych obserwacji."],
                    ["Trend","trend_score","Siła trendu cenowego od −100 (silny spadek) do +100 (silny wzrost). Liczone z EMA20/50/200 i momentum."],
                    ["Sent.","sentiment_score","Wynik sentymentu newsów od −100 do +100. Bazuje na NLP (FinBERT lub heurystyka keyword-based)."],
                    ["Kruchość","fragility_score","Miara niestabilności układu — wysokość wahań, rozbieżność sygnałów, zmienność sentymentu. >60 = ostrzeżenie."],
                    ["Reżim","regime","Aktualny reżim rynkowy: trending_up, trending_down, ranging, volatile. Ustalany przez kombinator sygnałów."],
                    ["Prog 5d","forecast_up_5d","Prawdopodobieństwo wzrostu ceny w ciągu 5 dni roboczych wg modelu heurystycznego. >50% = bullish."],
                    ["Prog 20d","forecast_up_20d","Prawdopodobieństwo wzrostu w ciągu 20 dni (1 miesiąc). Horyzont długoterminowy."],
                    ["Conv.","conviction_score","Conviction score z decision support 0–100. Siła przekonania o kierunku ruchu — im wyższy tym bardziej zdecydowany sygnał."],
                    ["Ryzyko","risk_score","Poziom ryzyka 0–100 z decision support. Wyższy = bardziej niebezpieczna pozycja. Uwzględnia kruchość, zmienność i dywergencje."],
                    ["ML 5d","ml_prob_up","Prawdopodobieństwo wzrostu za 5 dni wg modelu ML (Logistic Regression). Dostępne po wytrenowaniu modelu."],
                    ["Meta","meta_trade_probability","Skalibrowane P(opłacalnej transakcji) i dynamiczny próg uczony osobno dla rynku oraz reżimu."],
                    ["IV","implied_volatility","Implied Volatility (zmienność implikowana) opcji ATM z najbliższej serii. Wysoka IV (>40%) = rynek wycenia duże ryzyko. Niska IV (<15%) = spokój. Dostępna tylko dla US stocks i ETF."],
                    ["P/C","put_call_ratio","Put/Call Ratio — stosunek wolumenu put do call. >1.0 = dominacja put (niedźwiedzie), <0.5 = dominacja call (byki). Neutralnie ~0.7."],
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
                  const recColor = r.recommendation === "KUP" ? "#16a34a" : r.recommendation === "SPRZEDAJ" ? "#dc2626" : r.recommendation === "TRZYMAJ" ? "#b45309" : "#64748b";
                  const recBg   = r.recommendation === "KUP" ? "rgba(22,163,74,0.08)" : r.recommendation === "SPRZEDAJ" ? "rgba(220,38,38,0.08)" : r.recommendation === "TRZYMAJ" ? "rgba(180,87,9,0.07)" : "rgba(100,116,139,0.08)";
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
                      <td style={{ padding: "0.4rem 0.5rem", whiteSpace: "nowrap" }}>
                        <span style={{ color: r.expected_net_edge_pct > r.uncertainty_pct ? "#16a34a" : "#64748b" }}>
                          {r.expected_net_edge_pct.toFixed(2)}%
                        </span>
                        <div style={{ fontSize: "0.65rem", color: "var(--text-3)" }}>±{r.uncertainty_pct.toFixed(2)}% · koszt {r.transaction_cost_pct.toFixed(2)}%</div>
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.7rem", whiteSpace: "nowrap" }}>
                        {r.market_segment}/{r.regime}
                        <div style={{ color: "var(--text-3)" }}>{r.calibration_scope} · n={r.calibration_sample_size}</div>
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
                      <td style={{ padding: "0.4rem 0.5rem", color: r.meta_gate_applied ? "#dc2626" : "inherit" }}>
                        {r.meta_trade_probability != null ? (
                          <span title={r.meta_trade_threshold != null ? `próg ${r.meta_trade_threshold.toFixed(1)}% · ${r.meta_threshold_scope ?? "fallback"}` : undefined}>
                            {r.meta_trade_probability.toFixed(1)}%/{r.meta_trade_threshold?.toFixed(1) ?? "—"}%{r.meta_gate_applied ? " ⛔" : ""}
                          </span>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                        {r.implied_volatility != null ? (
                          <span style={{
                            color: r.implied_volatility > 50 ? "#dc2626" : r.implied_volatility > 30 ? "#b45309" : "#16a34a",
                            fontWeight: 500,
                          }}>
                            {r.implied_volatility.toFixed(1)}%
                          </span>
                        ) : <span style={{ color: "var(--text-3)" }}>—</span>}
                        {r.iv_rank != null && (
                          <div style={{ fontSize: "0.65rem", color: "var(--text-3)" }}>rank {r.iv_rank.toFixed(0)}</div>
                        )}
                      </td>
                      <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.75rem" }}>
                        {r.put_call_ratio != null ? (
                          <span style={{
                            color: r.put_call_ratio > 1.0 ? "#dc2626" : r.put_call_ratio < 0.5 ? "#16a34a" : "inherit",
                            fontWeight: r.put_call_ratio > 1.0 || r.put_call_ratio < 0.5 ? 600 : 400,
                          }}>
                            {r.put_call_ratio.toFixed(2)}
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

      </> /* koniec zakładki Rekomendacje */}

      {/* ── Zakładka Jakość danych ──────────────────────────────────────────── */}
      {activeTab === "quality" && <>
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
            <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:"0.4rem" }}>
              <button
                onClick={async () => {
                  setEnrichAllBusy(true);
                  try {
                    const r = await api.enrichAllNews();
                    const total = r.enriched;
                    alert(`NLP enrichment zakończony: +${total} newsów`);
                    const dq = await api.dataQuality().catch(() => null);
                    if (dq) setDataQuality(dq);
                  } catch (err) {
                    alert(`Błąd: ${err instanceof Error ? err.message : err}`);
                  } finally {
                    setEnrichAllBusy(false);
                  }
                }}
                disabled={enrichAllBusy}
                style={{ fontSize:"0.75rem", padding:"0.25rem 0.75rem", background:"#1e3a5f", color:"#fff", border:"none", borderRadius:"4px", cursor:"pointer", opacity: enrichAllBusy ? 0.6 : 1 }}
              >
                {enrichAllBusy ? "Trwa NLP…" : "Uruchom NLP dla wszystkich"}
              </button>
            </div>
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
                      ["Trafne 7d","news.relevant_items_7d","Artykuły z ostatnich 7 dni, które przekroczyły próg trafności dla aktywa. Tylko one wpływają na rekomendację."],
                      ["Model NLP%","news.current_model_coverage_30d_pct","Pokrycie newsów z 30 dni aktualnym modelem NLP. Starsze wyniki są stopniowo przeliczane w tle."],
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
                      "news.relevant_items_7d": a.news.relevant_items_7d,
                      "news.current_model_coverage_30d_pct": a.news.current_model_coverage_30d_pct,
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
                          <div style={{ color: a.news.relevant_items_7d > 0 ? "#16a34a" : "#b45309" }}>
                            {a.news.relevant_items_7d}/{a.news.items_7d}
                          </div>
                          <div style={{ fontSize:"0.65rem", color:"var(--text-2)" }}>
                            rel. {a.news.relevance_mean_7d.toFixed(2)} · {a.news.source_count_7d} źr.
                          </div>
                        </td>
                        <td style={{ padding:"0.35rem 0.5rem" }} title={a.news.nlp_model}>
                          <span style={{ color: a.news.current_model_coverage_30d_pct>=70?"#16a34a":a.news.current_model_coverage_30d_pct>=30?"#b45309":"#dc2626" }}>
                            {a.news.current_model_coverage_30d_pct.toFixed(0)}%
                          </span>
                          {a.news.current_model_coverage_30d_pct < 70 && a.news.items_30d > 0 && (
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setEnrichingAsset(a.asset_id);
                                try {
                                  const r = await api.enrichNews(a.asset_id);
                                  alert(`NLP enrichment: +${r.enriched} newsów`);
                                  const dq = await api.dataQuality().catch(() => null);
                                  if (dq) setDataQuality(dq);
                                } catch (err) {
                                  alert(`Błąd: ${err instanceof Error ? err.message : err}`);
                                } finally {
                                  setEnrichingAsset(null);
                                }
                              }}
                              disabled={enrichingAsset === a.asset_id}
                              style={{ display:"block", marginTop:"0.2rem", fontSize:"0.6rem", padding:"1px 5px", background:"#1e3a5f", color:"#fff", border:"none", borderRadius:"3px", cursor:"pointer", opacity: enrichingAsset === a.asset_id ? 0.6 : 1 }}
                            >
                              {enrichingAsset === a.asset_id ? "…" : "NLP"}
                            </button>
                          )}
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
      </> /* koniec zakładki Jakość danych */}

      {/* ── Sekcje dodatkowe w zakładce Analizy (heurystyka vs ML, itd.) ───── */}
      {activeTab === "analysis" && <>
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
                          <th style={{ ...thS, textAlign: "left" }} data-tip="Nazwa modelu ML testowanego w walk-forward." data-tip-side="bottom">Model</th>
                          <th style={{ ...thS, textAlign: "right" }} data-tip="Accuracy — % poprawnych predykcji (TP+TN)/(całość). Powyżej 55% to dobry wynik dla rynków." data-tip-side="bottom" title="Accuracy — % poprawnych predykcji">Accuracy ⓘ</th>
                          <th style={{ ...thS, textAlign: "right" }} data-tip="Precision — % predykcji UP które naprawdę były wzrostami. Wysoka = mało fałszywych sygnałów." data-tip-side="bottom" title="Precision">Precision ⓘ</th>
                          <th style={{ ...thS, textAlign: "right" }} data-tip="Recall — % faktycznych wzrostów które model wykrył. Wysoki = mało pominiętych okazji." data-tip-side="bottom" title="Recall">Recall ⓘ</th>
                          <th style={{ ...thS, textAlign: "right" }} data-tip="F1-score — średnia harmoniczna Precision i Recall. Balansuje oba. >0.50 = dobry model." data-tip-side="bottom" title="F1-score">F1 ⓘ</th>
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
            <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginBottom: "0.75rem", maxHeight: "calc(6 * 4.2rem)", overflowY: "auto" }}>
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
        title="Historia narracji"
        subtitle="Ewolucja dominujących narracji rynkowych."
      >
        <NarrativeHistoryChart rows={narrativeHistory} />
      </Section>

      </> /* koniec sekcji dodatkowych zakładki Analizy */}

      {/* ── Zakładka Wyniki spółek ───────────────────────────────────────── */}
      {activeTab === "earnings" && (() => {
        const surpriseBadge = (label: string | null, pct: number | null) => {
          if (!label) return null;
          const colors: Record<string, { bg: string; color: string }> = {
            BEAT: { bg: "rgba(22,163,74,0.12)", color: "#16a34a" },
            MISS: { bg: "rgba(220,38,38,0.12)", color: "#dc2626" },
            MEET: { bg: "rgba(180,87,9,0.10)", color: "#b45309" },
          };
          const s = colors[label] ?? { bg: "var(--bg-subtle)", color: "var(--text-2)" };
          return (
            <span style={{
              padding: "0.15rem 0.45rem", borderRadius: "5px", fontSize: "0.72rem",
              fontWeight: 700, background: s.bg, color: s.color,
            }}>
              {label}{pct != null ? ` ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%` : ""}
            </span>
          );
        };

        const fmtDate = (d: string) =>
          new Date(d).toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" });
        const fmtEps = (v: number | null) => v != null ? v.toFixed(2) : "—";

        return (<>
          <Section title="Kalendarz wyników" subtitle="Nadchodzące raporty kwartalne śledzonych spółek.">
            {earningsCalendar.upcoming.length === 0 ? (
              <p style={{ color: "var(--text-3)", fontSize: "0.82rem" }}>
                Brak nadchodzących wyników. Uruchom synchronizację:
                <button style={{ marginLeft: "0.5rem", padding: "0.2rem 0.6rem", borderRadius: 5, border: "1px solid var(--border)", cursor: "pointer", fontSize: "0.78rem" }}
                  onClick={() => api.syncEarnings().then(() => refresh())}>
                  Sync Wyniki
                </button>
              </p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)" }}>
                      {([
                        ["Data",       "Planowana data publikacji raportu kwartalnego."],
                        ["Symbol",     "Ticker giełdowy spółki. Kliknij wiersz aby przejść do analizy."],
                        ["Spółka",     "Pełna nazwa spółki."],
                        ["EPS (est.)", "Oczekiwany zysk na akcję (Earnings Per Share) wg konsensusu analityków przed raportem."],
                        ["Kwartał",    "Okres fiskalny którego dotyczy raport, np. 2025Q1 = styczeń–marzec 2025."],
                      ] as [string,string][]).map(([h, tip]) => (
                        <th key={h} data-tip={tip} data-tip-side="bottom" style={{ padding: "0.3rem 0.5rem", textAlign: "left", fontSize: "0.72rem", color: "var(--text-2)", cursor: "help", whiteSpace: "nowrap" }}>
                          {h} <span style={{ opacity: 0.45, fontSize: "0.6rem" }}>ⓘ</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {earningsCalendar.upcoming.map((e, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                        onClick={() => { setSelectedAsset(e.asset_id); setActiveTab("analysis"); }}>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: 600 }}>{fmtDate(e.report_date)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--accent)", fontWeight: 700 }}>{e.symbol}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{e.name}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{fmtEps(e.eps_estimate)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-3)", fontSize: "0.72rem" }}>{e.fiscal_period ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Ostatnie wyniki — zaskoczenia" subtitle="Raporty z ostatnich 8 tygodni. Kliknij wiersz aby przejść do aktywa.">
            {earningsCalendar.recent.length === 0 ? (
              <p style={{ color: "var(--text-3)", fontSize: "0.82rem" }}>
                Brak ostatnich wyników. Kliknij <strong>Sync Wyniki</strong> powyżej.
              </p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)" }}>
                      {([
                        ["Data",          "Data opublikowania raportu kwartalnego."],
                        ["Symbol",        "Ticker giełdowy spółki. Kliknij wiersz aby przejść do analizy."],
                        ["Spółka",        "Pełna nazwa spółki."],
                        ["EPS est.",      "Prognoza zysku na akcję wg konsensusu analityków przed raportem."],
                        ["EPS aktual.",   "Rzeczywisty zysk na akcję opublikowany w raporcie."],
                        ["Niespodzianka", "BEAT = wyniki powyżej oczekiwań (zielony), MISS = poniżej (czerwony), MEET = zgodnie z prognozą (pomarańczowy). Liczba % to odchylenie: (aktual−est)/|est|×100."],
                        ["Kwartał",       "Okres fiskalny którego dotyczy raport."],
                      ] as [string,string][]).map(([h, tip]) => (
                        <th key={h} data-tip={tip} data-tip-side="bottom" style={{ padding: "0.3rem 0.5rem", textAlign: "left", fontSize: "0.72rem", color: "var(--text-2)", cursor: "help", whiteSpace: "nowrap" }}>
                          {h} <span style={{ opacity: 0.45, fontSize: "0.6rem" }}>ⓘ</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {earningsCalendar.recent.map((e, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                        onClick={() => { setSelectedAsset(e.asset_id); setActiveTab("analysis"); }}>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{fmtDate(e.report_date)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--accent)", fontWeight: 700 }}>{e.symbol}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{e.name}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{fmtEps(e.eps_estimate)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: 600 }}>{fmtEps(e.eps_actual)}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{surpriseBadge(e.surprise_label, e.eps_surprise_pct)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-3)", fontSize: "0.72rem" }}>{e.fiscal_period ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title={`Szczegóły: ${assets.find(a => a.id === selectedAsset)?.name ?? selectedAsset}`}
            subtitle="Historia wyników kwartalnych dla wybranego aktywa.">
            {assetEarnings.length === 0 ? (
              <p style={{ color: "var(--text-3)", fontSize: "0.82rem" }}>Brak danych wynikowych dla tego aktywa.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)" }}>
                      {([
                        ["Kwartał",       "Okres fiskalny raportu, np. 2025Q1 = styczeń–marzec 2025."],
                        ["Data",          "Data opublikowania lub planowana data raportu."],
                        ["EPS est.",      "Prognoza zysku na akcję wg analityków przed raportem."],
                        ["EPS aktual.",   "Rzeczywisty EPS z raportu. Pogrubiony gdy dostępny."],
                        ["Niespodzianka", "BEAT/MISS/MEET i % odchylenia od prognozy. Brak gdy raport jeszcze nie opublikowany."],
                        ["Status",        "Czy raport został już opublikowany (✓ opublikowany) czy jest jeszcze przed nami (oczekiwany)."],
                      ] as [string,string][]).map(([h, tip]) => (
                        <th key={h} data-tip={tip} data-tip-side="bottom" style={{ padding: "0.3rem 0.5rem", textAlign: "left", fontSize: "0.72rem", color: "var(--text-2)", cursor: "help", whiteSpace: "nowrap" }}>
                          {h} <span style={{ opacity: 0.45, fontSize: "0.6rem" }}>ⓘ</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {assetEarnings.map((e, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: 600 }}>{e.fiscal_period ?? "—"}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{fmtDate(e.report_date)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", color: "var(--text-2)" }}>{fmtEps(e.eps_estimate)}</td>
                        <td style={{ padding: "0.3rem 0.5rem", fontWeight: e.eps_actual != null ? 600 : 400 }}>{fmtEps(e.eps_actual)}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{surpriseBadge(e.surprise_label, e.eps_surprise_pct)}</td>
                        <td style={{ padding: "0.3rem 0.5rem" }}>
                          {e.is_upcoming
                            ? <span style={{ color: "var(--text-3)", fontSize: "0.72rem" }}>oczekiwany</span>
                            : <span style={{ color: "#16a34a", fontSize: "0.72rem" }}>✓ opublikowany</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* ── Analiza LLM wyników kwartalnych ── */}
          <Section title="Analiza AI wyników kwartalnych"
            subtitle="Claude analizuje newsy z okolicy raportu i ocenia ton zarządu, kierunek prognoz i kluczowe tematy.">
            <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", marginBottom: "0.8rem", flexWrap: "wrap" }}>
              <button
                disabled={llmAnalyzeLoading}
                style={{ padding: "0.3rem 0.8rem", borderRadius: 6, border: "1px solid var(--border)", cursor: llmAnalyzeLoading ? "not-allowed" : "pointer", fontSize: "0.78rem", opacity: llmAnalyzeLoading ? 0.6 : 1 }}
                onClick={async () => {
                  setLlmAnalyzeLoading(true);
                  try {
                    const result = await api.analyzeLatestEarnings(selectedAsset);
                    setEarningsAnalyses(prev => {
                      const without = prev.filter(a => a.earnings_id !== result.earnings_id);
                      return [result, ...without];
                    });
                  } catch (e) {
                    setError("Analiza LLM niedostępna. Sprawdź klucz ANTHROPIC_API_KEY w .env.");
                  } finally {
                    setLlmAnalyzeLoading(false);
                  }
                }}>
                {llmAnalyzeLoading ? "Analizuję..." : "Analizuj AI (najnowsze)"}
              </button>
              <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
                Wymaga klucza ANTHROPIC_API_KEY i newsów w bazie.
              </span>
            </div>
            {earningsAnalyses.length === 0 ? (
              <p style={{ color: "var(--text-3)", fontSize: "0.82rem" }}>
                Brak analiz AI dla tego aktywa. Kliknij "Analizuj AI" powyżej.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {earningsAnalyses.map((a) => {
                  const sentColor = a.llm_sentiment_score > 20 ? "#16a34a" : a.llm_sentiment_score < -20 ? "#dc2626" : "var(--text-2)";
                  const toneLabels = ["", "Bardzo niedźwiedzi", "Niedźwiedzi", "Neutralny", "Bycze", "Bardzo bycze"];
                  const guidanceColors: Record<string, string> = {
                    raised: "#16a34a", lowered: "#dc2626", maintained: "var(--text-2)", none: "var(--text-3)"
                  };
                  const guidanceLabels: Record<string, string> = {
                    raised: "Prognozy podniesione", lowered: "Prognozy obniżone",
                    maintained: "Prognozy bez zmian", none: "Brak prognoz"
                  };
                  return (
                    <div key={a.id} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.9rem 1.1rem", background: "var(--bg-subtle)" }}>
                      <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.6rem" }}>
                        <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>
                          {assets.find(asset => asset.id === a.asset_id)?.name ?? a.asset_id}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
                          Analiza: {new Date(a.analyzed_at).toLocaleDateString("pl-PL")}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
                          Newsy: {a.news_articles_used}
                        </span>
                        <span style={{ fontSize: "0.72rem", padding: "0.1rem 0.4rem", borderRadius: 4, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-3)" }}>
                          {a.model_used}
                        </span>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.6rem", marginBottom: "0.7rem" }}>
                        <div style={{ background: "var(--bg)", borderRadius: 6, padding: "0.5rem 0.7rem" }}>
                          <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginBottom: "0.15rem" }}>Ton zarządu</div>
                          <div style={{ fontWeight: 700 }}>{"★".repeat(a.tone_score)}{"☆".repeat(5 - a.tone_score)}</div>
                          <div style={{ fontSize: "0.72rem", color: "var(--text-2)" }}>{toneLabels[a.tone_score] ?? ""}</div>
                        </div>
                        <div style={{ background: "var(--bg)", borderRadius: 6, padding: "0.5rem 0.7rem" }}>
                          <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginBottom: "0.15rem" }}>Kierunek prognoz</div>
                          <div style={{ fontWeight: 700, color: guidanceColors[a.guidance_change] ?? "var(--text)" }}>
                            {guidanceLabels[a.guidance_change] ?? a.guidance_change}
                          </div>
                        </div>
                        <div style={{ background: "var(--bg)", borderRadius: 6, padding: "0.5rem 0.7rem" }}>
                          <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginBottom: "0.15rem" }}>Sentyment AI</div>
                          <div style={{ fontWeight: 700, fontSize: "1.1rem", color: sentColor }}>
                            {a.llm_sentiment_score > 0 ? "+" : ""}{a.llm_sentiment_score.toFixed(1)}
                          </div>
                          <div style={{ fontSize: "0.68rem", color: "var(--text-3)" }}>zakres -100 do +100</div>
                        </div>
                      </div>

                      <div style={{ fontSize: "0.8rem", color: "var(--text)", lineHeight: 1.5, marginBottom: "0.6rem" }}>
                        {a.summary}
                      </div>

                      {a.key_quote && (
                        <div style={{ borderLeft: "3px solid var(--accent)", paddingLeft: "0.6rem", marginBottom: "0.6rem", fontSize: "0.78rem", color: "var(--text-2)", fontStyle: "italic" }}>
                          {a.key_quote}
                        </div>
                      )}

                      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                        {a.key_themes.length > 0 && (
                          <div>
                            <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginBottom: "0.25rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Kluczowe tematy</div>
                            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                              {a.key_themes.map((t, i) => (
                                <span key={i} style={{ padding: "0.1rem 0.45rem", borderRadius: 4, background: "rgba(99,102,241,0.1)", color: "#6366f1", fontSize: "0.72rem" }}>{t}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {a.risk_factors.length > 0 && (
                          <div>
                            <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginBottom: "0.25rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Czynniki ryzyka</div>
                            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                              {a.risk_factors.map((r, i) => (
                                <span key={i} style={{ padding: "0.1rem 0.45rem", borderRadius: 4, background: "rgba(220,38,38,0.08)", color: "#dc2626", fontSize: "0.72rem" }}>{r}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>
        </>);
      })()}

      {/* ── Zakładka Insider & Short ──────────────────────────────────────── */}
      {activeTab === "insider" && (() => {
        const latestSI = shortInterest[0] ?? null;
        const syncInsider = async () => {
          setSyncingInsider(true);
          try {
            const res = await api.syncInsiderAsset(selectedAsset);
            setInfo(`Zsynchronizowano: ${res.insider_trades} transakcji, ${res.short_interest} short interest`);
            const [trades, si] = await Promise.all([
              api.insiderTrades(selectedAsset).catch(() => []),
              api.shortInterest(selectedAsset).catch(() => []),
            ]);
            setInsiderTrades(trades);
            setShortInterest(si);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          } finally {
            setSyncingInsider(false);
          }
        };

        const buySellColor = (t: InsiderTrade) =>
          t.transaction_type === "buy" ? "#16a34a" : t.transaction_type === "sell" ? "#dc2626" : "var(--text-2)";

        return (
          <>
            {/* Header toolbar */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700, fontSize: "1rem" }}>Insider Trades &amp; Short Interest</span>
              <button
                onClick={syncInsider}
                disabled={syncingInsider}
                style={{ padding: "4px 14px", borderRadius: 6, border: "1px solid var(--border)", background: syncingInsider ? "var(--surface)" : "var(--accent)", color: syncingInsider ? "var(--text-3)" : "#fff", cursor: syncingInsider ? "not-allowed" : "pointer", fontSize: "0.8rem" }}
              >
                {syncingInsider ? "Sync…" : "Synchronizuj"}
              </button>
              <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Źródło: Finnhub (insider) + yfinance (short interest)</span>
            </div>

            {/* Short Interest panel */}
            <Section title="Short Interest" subtitle="Liczba akcji sprzedanych krótko (short selling). Wysoki short % może sygnalizować presję niedźwiedzi lub potencjalny short squeeze.">
              {latestSI === null ? (
                <div style={{ color: "var(--text-3)", fontSize: "0.85rem", padding: "1rem 0" }}>
                  Brak danych short interest. Kliknij "Synchronizuj" aby pobrać.
                </div>
              ) : (
                <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
                  <div style={{ textAlign: "center", minWidth: 120 }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>Short % Float</div>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700, color: (latestSI.short_percent_float ?? 0) > 0.1 ? "#dc2626" : "var(--text)" }}>
                      {latestSI.short_percent_float != null ? `${(latestSI.short_percent_float * 100).toFixed(1)}%` : "—"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)" }}>wg float</div>
                  </div>
                  <div style={{ textAlign: "center", minWidth: 120 }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>Short Ratio</div>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700, color: (latestSI.short_ratio ?? 0) > 5 ? "#f59e0b" : "var(--text)" }}>
                      {latestSI.short_ratio != null ? latestSI.short_ratio.toFixed(1) : "—"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)" }}>dni do pokrycia</div>
                  </div>
                  <div style={{ textAlign: "center", minWidth: 120 }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>Akcji short</div>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>
                      {latestSI.shares_short != null ? (latestSI.shares_short >= 1e6 ? `${(latestSI.shares_short / 1e6).toFixed(1)}M` : latestSI.shares_short.toLocaleString()) : "—"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-3)" }}>stan na {latestSI.report_date}</div>
                  </div>
                </div>
              )}
              {shortInterest.length > 1 && (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ background: "var(--surface)" }}>
                      {[["Data", "Data raportu"], ["Short %", "% akcji w free float sprzedanych krótko"], ["Short Ratio", "Liczba dni potrzebnych do pokrycia pozycji krótkich przy średnim wolumenie"], ["Akcji short", "Łączna liczba akcji sprzedanych krótko"]].map(([h, tip]) => (
                        <th key={h} data-tip={tip} data-tip-side="bottom" style={{ padding: "4px 8px", textAlign: "left", fontWeight: 600, cursor: "help" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shortInterest.map((si) => (
                      <tr key={si.id} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "4px 8px" }}>{si.report_date}</td>
                        <td style={{ padding: "4px 8px", color: (si.short_percent_float ?? 0) > 0.1 ? "#dc2626" : "var(--text)" }}>
                          {si.short_percent_float != null ? `${(si.short_percent_float * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td style={{ padding: "4px 8px", color: (si.short_ratio ?? 0) > 5 ? "#f59e0b" : "var(--text)" }}>
                          {si.short_ratio != null ? si.short_ratio.toFixed(1) : "—"}
                        </td>
                        <td style={{ padding: "4px 8px" }}>
                          {si.shares_short != null ? (si.shares_short >= 1e6 ? `${(si.shares_short / 1e6).toFixed(1)}M` : si.shares_short.toLocaleString()) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Section>

            {/* Insider Trades panel */}
            <Section title="Transakcje insiderów" subtitle="Transakcje akcjami spółki przez osoby posiadające dostęp do informacji poufnych (zarząd, rada nadzorcza). Zakupy mogą sygnalizować przekonanie o niedowartościowaniu, sprzedaże — realizację zysku lub potrzebę gotówki.">
              {insiderTrades.length === 0 ? (
                <div style={{ color: "var(--text-3)", fontSize: "0.85rem", padding: "1rem 0" }}>
                  Brak danych insider transactions. Kliknij "Synchronizuj" aby pobrać z Finnhub.
                </div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ background: "var(--surface)" }}>
                      {[
                        ["Data", "Data transakcji"],
                        ["Osoba", "Imię i nazwisko insiders"],
                        ["Typ", "Kod i typ transakcji (P=kupno, S=sprzedaż, M=konwersja opcji)"],
                        ["Akcji", "Liczba akcji objętych transakcją"],
                        ["Cena", "Cena wykonania transakcji"],
                        ["Wartość", "Szacowana wartość transakcji (akcji × cena)"],
                        ["Data zgł.", "Data złożenia raportu do regulatora (SEC Form 4)"],
                      ].map(([h, tip]) => (
                        <th key={h} data-tip={tip} data-tip-side="bottom" style={{ padding: "4px 8px", textAlign: "left", fontWeight: 600, cursor: "help" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {insiderTrades.map((t) => (
                      <tr key={t.id} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "4px 8px", whiteSpace: "nowrap" }}>{t.transaction_date}</td>
                        <td style={{ padding: "4px 8px", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t.name}>{t.name}</td>
                        <td style={{ padding: "4px 8px", whiteSpace: "nowrap" }}>
                          <span style={{
                            padding: "2px 7px", borderRadius: 4, fontSize: "0.72rem", fontWeight: 600,
                            background: t.transaction_type === "buy" ? "rgba(22,163,74,0.12)" : t.transaction_type === "sell" ? "rgba(220,38,38,0.1)" : "var(--surface)",
                            color: buySellColor(t),
                          }}>
                            {t.transaction_code} · {t.transaction_type === "buy" ? "Kupno" : t.transaction_type === "sell" ? "Sprzedaż" : "Inne"}
                          </span>
                        </td>
                        <td style={{ padding: "4px 8px", textAlign: "right", color: buySellColor(t) }}>
                          {t.shares != null ? (t.shares >= 1e6 ? `${(t.shares / 1e6).toFixed(2)}M` : t.shares.toLocaleString()) : "—"}
                        </td>
                        <td style={{ padding: "4px 8px", textAlign: "right" }}>
                          {t.price != null ? `$${t.price.toFixed(2)}` : "—"}
                        </td>
                        <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 500, color: buySellColor(t) }}>
                          {t.value != null ? (Math.abs(t.value) >= 1e6 ? `$${(t.value / 1e6).toFixed(2)}M` : `$${Math.abs(t.value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`) : "—"}
                        </td>
                        <td style={{ padding: "4px 8px", whiteSpace: "nowrap", color: "var(--text-3)" }}>{t.filing_date ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Section>
          </>
        );
      })()}

      {/* ── Zakładka Top Picks ───────────────────────────────────────────── */}
      {activeTab === "toppicks" && (
        <Section
          title="Top Picks — najlepsze z najlepszych"
          subtitle="Aktywa, w których wszystkie sygnały wskazują kierunek wzrostowy z najwyższą zbieżnością. Wymagane: rekomendacja KUP, composite ≥ 65, co najmniej 6/9 sygnałów i pewność ≥ 62%."
        >
          {topPicks.length === 0 ? (
            <div style={{ padding: "2rem 0", textAlign: "center", color: "var(--text-3)", fontSize: "0.9rem" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>⭐</div>
              <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Brak Top Picks w tej chwili</div>
              <div>Żadne aktywo nie spełnia wszystkich kryteriów. Odśwież dane lub poczekaj na kolejny cykl analizy.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {topPicks.map((pick, idx) => {
                const medal = idx === 0 ? { bg: "rgba(251,191,36,0.12)", border: "#f59e0b", icon: "🥇" }
                            : idx === 1 ? { bg: "rgba(148,163,184,0.1)", border: "#94a3b8", icon: "🥈" }
                            : idx === 2 ? { bg: "rgba(180,120,60,0.1)", border: "#b45309", icon: "🥉" }
                            : { bg: "var(--surface)", border: "var(--border)", icon: "⭐" };

                const certaintyPct = pick.certainty_score.toFixed(1);
                const certaintyColor = pick.certainty_score >= 80 ? "#16a34a"
                                     : pick.certainty_score >= 70 ? "#2563eb"
                                     : "#f59e0b";

                const recColor = pick.recommendation === "KUP" ? "#16a34a"
                               : pick.recommendation === "SPRZEDAJ" ? "#dc2626"
                               : "#f59e0b";

                const assetCurr = assetCurrencyMap.get(pick.asset_id) ?? "USD";
                const priceStr = pick.last_price != null ? fmtPrice(pick.last_price, assetCurr) : "—";
                const priceLabel = pick.last_price != null ? displayLabel(assetCurr) : "";

                return (
                  <div
                    key={pick.asset_id}
                    style={{
                      background: medal.bg,
                      border: `1.5px solid ${medal.border}`,
                      borderRadius: 10,
                      padding: "1rem 1.25rem",
                    }}
                  >
                    {/* Header row */}
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", marginBottom: "0.75rem" }}>
                      <div style={{ fontSize: "1.8rem", lineHeight: 1 }}>{medal.icon}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>
                            #{idx + 1} {pick.name}
                          </span>
                          <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-3)", background: "var(--surface)", padding: "1px 6px", borderRadius: 4 }}>
                            {pick.symbol}
                          </span>
                          <span style={{ fontSize: "0.78rem", fontWeight: 700, color: recColor, background: `${recColor}18`, padding: "2px 8px", borderRadius: 4 }}>
                            {pick.recommendation}
                          </span>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-3)", marginLeft: "auto" }}>
                            {pick.regime}
                          </span>
                        </div>

                        {/* Certainty score bar */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.4rem" }}>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-3)", whiteSpace: "nowrap" }}>Pewność:</span>
                          <div style={{ flex: 1, height: 8, background: "var(--border)", borderRadius: 4, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${pick.certainty_score}%`, background: certaintyColor, borderRadius: 4, transition: "width 0.4s" }} />
                          </div>
                          <span style={{ fontWeight: 700, color: certaintyColor, fontSize: "0.92rem", whiteSpace: "nowrap" }}>
                            {certaintyPct}%
                          </span>
                        </div>

                        {/* Signals aligned */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.25rem" }}>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-3)", whiteSpace: "nowrap" }}>Sygnały:</span>
                          {Array.from({ length: pick.max_signals }).map((_, i) => {
                            const isAligned = i < pick.signals_aligned;
                            return (
                              <div
                                key={i}
                                style={{
                                  width: 10, height: 10, borderRadius: 2,
                                  background: isAligned ? "#16a34a" : "var(--border)",
                                  transition: "background 0.2s",
                                }}
                                title={isAligned ? (pick.aligned_labels[i] ?? "") : (pick.missing_labels[i - pick.signals_aligned] ?? "brak sygnału")}
                              />
                            );
                          })}
                          <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#16a34a" }}>
                            {pick.signals_aligned}/{pick.max_signals}
                          </span>
                        </div>
                      </div>

                      {/* Price + KPI */}
                      <div style={{ textAlign: "right", minWidth: 90 }}>
                        <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{priceStr}</div>
                        {priceLabel && <div style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>{priceLabel}</div>}
                        <div style={{ fontSize: "0.78rem", marginTop: "0.3rem", color: "var(--text-3)" }}>
                          Composite: <span style={{ fontWeight: 600, color: "var(--text)" }}>{pick.composite_score.toFixed(0)}</span>
                        </div>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-3)" }}>
                          Conviction: <span style={{ fontWeight: 600, color: "var(--text)" }}>{pick.conviction_score != null ? pick.conviction_score.toFixed(0) : "—"}</span>
                        </div>
                      </div>
                    </div>

                    {/* Signal checklist */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "0.75rem" }}>
                      {pick.aligned_labels.map(label => (
                        <span key={label} style={{
                          fontSize: "0.72rem", padding: "2px 8px", borderRadius: 12,
                          background: "rgba(22,163,74,0.1)", color: "#16a34a",
                          border: "1px solid rgba(22,163,74,0.25)", fontWeight: 500,
                          display: "inline-flex", alignItems: "center", gap: 3,
                        }}>
                          ✓ {label}
                        </span>
                      ))}
                      {pick.missing_labels.map(label => (
                        <span key={label} style={{
                          fontSize: "0.72rem", padding: "2px 8px", borderRadius: 12,
                          background: "var(--surface)", color: "var(--text-3)",
                          border: "1px solid var(--border)", fontWeight: 400,
                          display: "inline-flex", alignItems: "center", gap: 3,
                        }}>
                          · {label}
                        </span>
                      ))}
                    </div>

                    {/* Metrics row */}
                    <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", marginBottom: "0.6rem", fontSize: "0.8rem" }}>
                      {[
                        ["Trend", `${pick.trend_score.toFixed(0)}`, pick.trend_score >= 55 ? "#16a34a" : "var(--text-3)"],
                        ["Sentiment", `${pick.sentiment_score.toFixed(0)}`, pick.sentiment_score >= 50 ? "#16a34a" : "var(--text-3)"],
                        ["Fragility", `${pick.fragility_score.toFixed(0)}`, pick.fragility_score <= 40 ? "#16a34a" : "#dc2626"],
                        ["Ryzyko", pick.risk_score != null ? `${pick.risk_score.toFixed(0)}` : "—", (pick.risk_score ?? 100) <= 40 ? "#16a34a" : "#dc2626"],
                        ["ML 5d", pick.ml_prob_up != null ? `${pick.ml_prob_up.toFixed(0)}%↑` : "—", (pick.ml_prob_up ?? 0) >= 60 ? "#16a34a" : "var(--text-3)"],
                        ["ML 20d", pick.ml_20d_prob_up != null ? `${pick.ml_20d_prob_up.toFixed(0)}%↑` : "—", (pick.ml_20d_prob_up ?? 0) >= 60 ? "#16a34a" : "var(--text-3)"],
                        ["Prog 5d", pick.forecast_dir_5d ?? "—", pick.forecast_dir_5d === "up" ? "#16a34a" : pick.forecast_dir_5d === "down" ? "#dc2626" : "var(--text-3)"],
                        ["Prog 20d", pick.forecast_dir_20d ?? "—", pick.forecast_dir_20d === "up" ? "#16a34a" : pick.forecast_dir_20d === "down" ? "#dc2626" : "var(--text-3)"],
                      ].map(([lbl, val, color]) => (
                        <div key={lbl} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 55 }}>
                          <span style={{ color: "var(--text-3)", fontSize: "0.7rem" }}>{lbl}</span>
                          <span style={{ fontWeight: 600, color: color as string }}>{val}</span>
                        </div>
                      ))}
                    </div>

                    {/* Rationale */}
                    {pick.rationale && (
                      <div style={{ fontSize: "0.8rem", color: "var(--text-2)", lineHeight: 1.5, borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                        {pick.rationale}
                      </div>
                    )}

                    {/* Navigate */}
                    <div style={{ marginTop: "0.5rem", textAlign: "right" }}>
                      <button
                        onClick={() => { setSelectedAsset(pick.asset_id); setActiveTab("analysis"); }}
                        style={{
                          fontSize: "0.75rem", padding: "3px 12px", borderRadius: 6,
                          border: `1px solid ${medal.border}`, background: "transparent",
                          color: "var(--text)", cursor: "pointer", fontWeight: 500,
                        }}
                      >
                        Otwórz analizę →
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>
      )}

      {/* ── Zakładka Intraday ─────────────────────────────────────────────── */}
      {activeTab === "intraday" && (
        <IntradayTab assets={assets} selectedAssetId={selectedAsset} />
      )}

      {/* ── Zakładka Symulator ───────────────────────────────────────────── */}
      {activeTab === "simulator" && (
        <SimulatorTab assets={assets} selectedAssetId={selectedAsset} />
      )}

      {activeTab === "paper" && (
        <PaperTradingTab assets={assets} selectedAssetId={selectedAsset} />
      )}

      {activeTab === "calibration" && <CalibrationAuditTab />}

      {/* ── Zakładka Alerty SMS ───────────────────────────────────────────── */}
      {activeTab === "alerts-config" && (
        <AlertsConfigTab />
      )}

      </Suspense>

    </PageContainer>
  );}
