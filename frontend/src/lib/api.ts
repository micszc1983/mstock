import type {
  AnomalyScore,
  AnomalyHistoryPoint,
  InsiderSentiment,
  PEADAnalysis,
  IntradayBacktest,
  IntradayAIAnalysis,
  SmsAlertConfig,
  AggregateDashboardResponse,
  AssetCreate,
  AlertItem,
  Asset,
  CompareAssetsResponse,
  DecisionSnapshot,
  Forecast,
  ForecastQualitySummary,
  MLBacktest,
  MLDatasetStats,
  MLModelRun,
  MLPrediction,
  MLStatus,
  NarrativePoint,
  NotificationChannel,
  NotificationEvent,
  Preference,
  ReportResponse,
  StoredThesis,
  StrategyComparison,
  ThesisOutcome,
  ThesisQualityByHorizon,
  ThesisQualitySummary,
  WalkForwardBacktest,
  AssetDataQuality,
  AssetRecommendation,
  PriceBar,
  EnsembleLeaderboard,
  EnsembleSignal,
  DynamicWeightInfo,
  DataQualityReport,
  MLExplanation,
  MLModelComparison,
  MLMonitor,
  Watchlist,
  EarningsCalendarResponse,
  EarningsRecord,
  EarningsCallAnalysis,
  InsiderTrade,
  ShortInterest,
  TopPick,
  IntradayCandle,
  IntradaySignalsResponse,
  IntradayFullResponse,
  SimulatorPerformance,
  PaperAccount,
  PaperOrder,
  PaperJournal,
  RecommendationAudit,
  RecommendationJournalRecord,
} from "./types";

// Jeśli otwarto z innego hosta niż localhost (np. 192.168.x.x), używaj tego samego hosta
// żeby żądania API trafiały do serwera MStock, nie do localhost obcego urządzenia.
function _defaultApiBase(): string {
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h !== "localhost" && h !== "127.0.0.1") return `http://${h}:8000`;
  }
  return "http://127.0.0.1:8000";
}
export const API_BASE = _defaultApiBase();
export const adminHeaders = (): HeadersInit => {
  const key = import.meta.env.VITE_ADMIN_API_KEY;
  return key ? { "X-Admin-Key": key } : {};
};

// Pozwala App.tsx aktualizować base URL gdy user zmieni pole Backend
let _activeBase = API_BASE;
export function setApiBaseUrl(url: string) { _activeBase = url.replace(/\/$/, ""); }
export function getApiBaseUrl() { return _activeBase; }

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { ...adminHeaders(), ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { ...adminHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    // Wyciągnij czytelny komunikat z FastAPI {detail: "..."}
    try {
      const err = await response.json();
      const msg = err?.detail ?? err?.message ?? `${response.status} ${response.statusText}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    } catch (parseErr) {
      if (parseErr instanceof Error && parseErr.message !== `${response.status} ${response.statusText}`) throw parseErr;
      throw new Error(`${response.status} ${response.statusText}`);
    }
  }
  return response.json();
}

export const api = {
  apiBase: API_BASE,

  assets: () => fetchJson<Asset[]>(`${_activeBase}/assets`),

  createAsset: (payload: AssetCreate) =>
    postJson<Asset>(`${_activeBase}/assets`, payload),

  deleteAsset: (assetId: string) =>
    fetch(`${_activeBase}/assets/${assetId}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    }),

  latestThesis: (assetId: string) =>
    fetchJson<StoredThesis>(`${_activeBase}/assets/${assetId}/theses/latest`),

  latestForecasts: (assetId: string) =>
    fetchJson<Forecast[]>(`${_activeBase}/assets/${assetId}/forecast`),

  forecastHistory: (assetId: string) =>
    fetchJson<Forecast[]>(`${_activeBase}/assets/${assetId}/forecast/history`),

  thesisOutcomes: (assetId: string) =>
    fetchJson<ThesisOutcome[]>(
      `${_activeBase}/assets/${assetId}/thesis-outcomes/history`
    ),

  thesisQualitySummary: (assetId: string) =>
    fetchJson<ThesisQualitySummary>(
      `${_activeBase}/assets/${assetId}/quality/thesis/summary`
    ),

  thesisQualityByHorizon: (assetId: string) =>
    fetchJson<ThesisQualityByHorizon[]>(
      `${_activeBase}/assets/${assetId}/quality/thesis/by-horizon`
    ),

  forecastQualitySummary: (assetId: string) =>
    fetchJson<ForecastQualitySummary[]>(
      `${_activeBase}/assets/${assetId}/quality/forecast/summary`
    ),

  narrativeHistory: (assetId: string, days = 14) =>
    fetchJson<NarrativePoint[]>(
      `${_activeBase}/assets/${assetId}/narratives?days=${days}`
    ),

  assetAlerts: (assetId: string) =>
    fetchJson<AlertItem[]>(`${_activeBase}/assets/${assetId}/alerts`),

  bootstrapAsset: (assetId: string) =>
    postJson<Record<string, unknown>>(
      `${_activeBase}/assets/${assetId}/bootstrap`
    ),

  decisionLatest: (assetId: string) =>
    fetchJson<DecisionSnapshot>(
      `${_activeBase}/assets/${assetId}/decision/latest`
    ),

  decisionHistory: (assetId: string) =>
    fetchJson<DecisionSnapshot[]>(
      `${_activeBase}/assets/${assetId}/decision/history`
    ),

  decisionRebuild: (assetId: string) =>
    postJson<DecisionSnapshot>(
      `${_activeBase}/assets/${assetId}/decision/rebuild`
    ),

  watchlists: () => fetchJson<Watchlist[]>(`${_activeBase}/watchlists`),

  createWatchlist: (
    name: string,
    description = "",
    isDefault = false
  ) =>
    postJson<Watchlist>(`${_activeBase}/watchlists`, {
      name,
      description,
      is_default: isDefault,
    }),

  addAssetToWatchlist: (watchlistId: number, assetId: string) =>
    postJson<Watchlist>(
      `${_activeBase}/watchlists/${watchlistId}/assets/${assetId}`
    ),

  removeAssetFromWatchlist: (watchlistId: number, assetId: string) =>
    fetch(`${_activeBase}/watchlists/${watchlistId}/assets/${assetId}`, {
      method: "DELETE",
    }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    }),

  deleteWatchlist: (watchlistId: number) =>
    fetch(`${_activeBase}/watchlists/${watchlistId}`, {
      method: "DELETE",
    }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    }),

  preferences: () => fetchJson<Preference[]>(`${_activeBase}/preferences`),

  upsertPreference: (preference_key: string, preference_value: string) =>
    postJson<Preference>(`${_activeBase}/preferences`, {
      preference_key,
      preference_value,
    }),

  aggregateDashboard: (assetIds: string[]) =>
    fetchJson<AggregateDashboardResponse>(
      `${_activeBase}/dashboard/aggregate?asset_ids=${assetIds.join(",")}`
    ),

  compareAssets: (assetIds: string[]) =>
    fetchJson<CompareAssetsResponse>(
      `${_activeBase}/compare/assets?asset_ids=${assetIds.join(",")}`
    ),

  createAssetReport: (assetId: string) =>
    postJson<ReportResponse>(`${_activeBase}/reports/daily/asset/${assetId}`),

  createWatchlistReport: (watchlistId: number) =>
    postJson<ReportResponse>(
      `${_activeBase}/reports/daily/watchlist/${watchlistId}`
    ),

  notificationChannels: () =>
    fetchJson<NotificationChannel[]>(`${_activeBase}/notification-channels`),

  createNotificationChannel: (
    channel_type: string,
    target: string,
    label: string,
    is_enabled = true
  ) =>
    postJson<NotificationChannel>(`${_activeBase}/notification-channels`, {
      channel_type,
      target,
      label,
      is_enabled,
    }),

  notificationEvents: () =>
    fetchJson<NotificationEvent[]>(`${_activeBase}/notification-events`),

  sendEmailNotification: (
    channelId: number,
    subject: string,
    message: string,
    assetId?: string
  ) =>
    postJson<Record<string, unknown>>(
      `${_activeBase}/notifications/email/${channelId}?subject=${encodeURIComponent(
        subject
      )}&message=${encodeURIComponent(message)}${
        assetId ? `&asset_id=${encodeURIComponent(assetId)}` : ""
      }`
    ),

  sendWhatsAppNotification: (
    channelId: number,
    message: string,
    assetId?: string
  ) =>
    postJson<Record<string, unknown>>(
      `${_activeBase}/notifications/whatsapp/${channelId}?message=${encodeURIComponent(
        message
      )}${assetId ? `&asset_id=${encodeURIComponent(assetId)}` : ""}`
    ),

  mlStatus: () => fetchJson<MLStatus>(`${_activeBase}/ml/status`),

  setMlMode: (ml_enabled: boolean) =>
    postJson<MLStatus>(`${_activeBase}/ml/mode`, { ml_enabled }),

  buildMlDataset: () =>
    postJson<{ built_rows: number; total_rows: number }>(
      `${_activeBase}/ml/dataset/build`
    ),

  mlDatasetStats: () =>
    fetchJson<MLDatasetStats>(`${_activeBase}/ml/dataset/stats`),

  trainMlModel: (
    target_name = "target_up_5d",
    model_name = "logistic_regression",
    asset_id: string | null = null,
    use_optuna = false,
    optuna_trials = 30,
  ) =>
    postJson<MLModelRun>(`${_activeBase}/ml/models/train`, {
      target_name,
      model_name,
      asset_id,
      use_optuna,
      optuna_trials,
    }),

  mlModels: () => fetchJson<MLModelRun[]>(`${_activeBase}/ml/models`),
  mlMonitoring: () => fetchJson<MLMonitor[]>(`${_activeBase}/ml/monitor`),
  runMlMonitoring: () => postJson<MLMonitor[]>(`${_activeBase}/ml/monitor/run`),

  runMlBacktest: (target_name = "target_up_5d", asset_id?: string) =>
    postJson<MLBacktest>(
      `${_activeBase}/ml/backtests/run?target_name=${encodeURIComponent(target_name)}${asset_id ? `&asset_id=${encodeURIComponent(asset_id)}` : ""}`
    ),

  mlBacktests: () => fetchJson<MLBacktest[]>(`${_activeBase}/ml/backtests`),

  scoreAssetMl: (assetId: string, target_name = "target_up_5d") =>
    postJson<MLPrediction>(
      `${_activeBase}/assets/${assetId}/ml/score?target_name=${encodeURIComponent(
        target_name
      )}`
    ),

  latestMlPrediction: (assetId: string, target_name = "target_up_5d") =>
    fetchJson<MLPrediction>(
      `${_activeBase}/assets/${assetId}/ml/prediction/latest?target_name=${encodeURIComponent(
        target_name
      )}`
    ),

  walkForwardBacktest: (target_name = "target_up_5d", asset_id?: string) =>
    postJson<WalkForwardBacktest>(
      `${_activeBase}/ml/backtests/walkforward?target_name=${encodeURIComponent(target_name)}${asset_id ? `&asset_id=${encodeURIComponent(asset_id)}` : ""}`
    ),

  compareHeuristicVsMl: (assetId: string) =>
    postJson<StrategyComparison>(
      `${_activeBase}/assets/${assetId}/evaluation/compare`
    ),

  latestHeuristicVsMl: (assetId: string) =>
    fetchJson<StrategyComparison>(
      `${_activeBase}/assets/${assetId}/evaluation/latest`
    ),

  allHeuristicVsMl: () =>
    fetchJson<StrategyComparison[]>(`${_activeBase}/evaluation/comparisons`),

  priceHistory: (assetId: string, limit = 90) =>
    fetchJson<PriceBar[]>(`${_activeBase}/assets/${assetId}/prices?limit=${limit}`),

  ensembleSignal: (assetId: string, mode = "ensemble_weighted") =>
    fetchJson<EnsembleSignal>(`${_activeBase}/assets/${assetId}/ensemble?mode=${mode}`),

  ensembleLeaderboard: () =>
    fetchJson<EnsembleLeaderboard[]>(`${_activeBase}/ensemble/leaderboard`),

  runPipeline: () =>
    fetchJson<{ message: string }>(`${_activeBase}/admin/run-pipeline`, { method: "POST" }),

  dataQuality: () =>
    fetchJson<DataQualityReport>(`${_activeBase}/data-quality`),

  assetDataQuality: (assetId: string) =>
    fetchJson<AssetDataQuality>(`${_activeBase}/assets/${assetId}/data-quality`),

  recommendations: () =>
    fetchJson<AssetRecommendation[]>(`${_activeBase}/recommendations`),

  assetRecommendation: (assetId: string) =>
    fetchJson<AssetRecommendation>(`${_activeBase}/assets/${assetId}/recommendation`),

  latestRecommendationAudit: () =>
    fetchJson<RecommendationAudit>(`${_activeBase}/recommendations/audit/latest`),

  runRecommendationAudit: (folds = 3) =>
    fetchJson<RecommendationAudit>(`${_activeBase}/admin/recommendations/audit?folds=${folds}`, { method: "POST" }),

  recommendationJournal: (limit = 200, assetId?: string) =>
    fetchJson<RecommendationJournalRecord[]>(
      `${_activeBase}/recommendations/journal?limit=${limit}${assetId ? `&asset_id=${encodeURIComponent(assetId)}` : ""}`
    ),

  snapshotRecommendationJournal: () =>
    fetchJson<{ inserted: number; evaluated: number }>(`${_activeBase}/admin/recommendations/journal/snapshot`, { method: "POST" }),

  trainAllMlModels: () =>
    postJson<Array<Record<string, unknown>>>(`${_activeBase}/ml/models/train-all`),

  trainMlChallengers: (assetId: string, targetName = "target_meta_label") =>
    postJson<Record<string, unknown>>(
      `${_activeBase}/ml/models/train-challengers?asset_id=${encodeURIComponent(assetId)}&target_name=${encodeURIComponent(targetName)}`
    ),

  mlExplain: (assetId: string, targetName = "target_up_5d") =>
    fetchJson<MLExplanation>(
      `${_activeBase}/assets/${assetId}/ml/explain?target_name=${encodeURIComponent(targetName)}`
    ),

  mlComparison: (targetName = "target_up_5d") =>
    fetchJson<MLModelComparison[]>(
      `${_activeBase}/ml/models/comparison?target_name=${encodeURIComponent(targetName)}`
    ),

  mlAvailableModels: () =>
    fetchJson<{ available: string[] }>(`${_activeBase}/ml/models/available`),

  enrichNews: (assetId: string, limit = 200) =>
    postJson<{ asset_id: string; enriched: number }>(
      `${_activeBase}/assets/${assetId}/news/enrich?limit=${limit}`
    ),

  enrichAllNews: (limitPerAsset = 200) =>
    postJson<{ enriched: number; per_asset: Record<string, number> }>(
      `${_activeBase}/news/enrich/all?limit_per_asset=${limitPerAsset}`
    ),

  earningsCalendar: () =>
    fetchJson<EarningsCalendarResponse>(`${_activeBase}/earnings/calendar`),

  assetEarnings: (assetId: string, limit = 8) =>
    fetchJson<EarningsRecord[]>(`${_activeBase}/assets/${assetId}/earnings?limit=${limit}`),

  syncEarnings: () =>
    postJson<{ started: boolean; message: string }>(`${_activeBase}/sync/earnings`),

  earningsAnalyses: (assetId: string, limit = 8) =>
    fetchJson<EarningsCallAnalysis[]>(`${_activeBase}/assets/${assetId}/earnings/analyses?limit=${limit}`),

  analyzeLatestEarnings: (assetId: string) =>
    postJson<EarningsCallAnalysis>(`${_activeBase}/assets/${assetId}/earnings/latest/analyze`),

  ensembleWeights: (assetId: string) =>
    fetchJson<DynamicWeightInfo>(`${_activeBase}/assets/${assetId}/ensemble/weights`),

  insiderTrades: (assetId: string, limit = 20) =>
    fetchJson<InsiderTrade[]>(`${_activeBase}/assets/${assetId}/insider-trades?limit=${limit}`),

  shortInterest: (assetId: string, limit = 6) =>
    fetchJson<ShortInterest[]>(`${_activeBase}/assets/${assetId}/short-interest?limit=${limit}`),

  syncInsiderAsset: (assetId: string) =>
    postJson<{ asset_id: string; insider_trades: number; short_interest: number }>(
      `${_activeBase}/assets/${assetId}/sync/insider`
    ),

  syncInsiderAll: () =>
    postJson<{ started: boolean; message: string }>(`${_activeBase}/sync/insider`),

  portfolioPositions: () =>
    fetchJson<{ asset_id: string; quantity: number; avg_buy_price: number | null }[]>(
      `${_activeBase}/portfolio/positions`
    ),

  topPicks: () =>
    fetchJson<TopPick[]>(`${_activeBase}/top-picks`),

  intradayCandles: (assetId: string, resolution = "15", limit = 200) =>
    fetchJson<IntradayCandle[]>(
      `${_activeBase}/assets/${assetId}/intraday/candles?resolution=${resolution}&limit=${limit}`
    ),

  intradaySignals: (assetId: string, resolution = "15") =>
    fetchJson<IntradaySignalsResponse>(
      `${_activeBase}/assets/${assetId}/intraday/signals?resolution=${resolution}`
    ),

  intradayRelativeStrength: (assetId: string, resolution = "15", benchmark = "qqq") =>
    fetchJson<import("./types").RelativeStrengthData>(
      `${_activeBase}/assets/${assetId}/intraday/relative-strength?resolution=${resolution}&benchmark=${benchmark}`
    ),

  intradayVolumeProfile: (assetId: string, resolution = "15", limit = 300) =>
    fetchJson<import("./types").VolumeProfile>(
      `${_activeBase}/assets/${assetId}/intraday/volume-profile?resolution=${resolution}&limit=${limit}`
    ),

  intradayFull: (assetId: string, resolution = "15") =>
    fetchJson<IntradayFullResponse>(
      `${_activeBase}/assets/${assetId}/intraday/full?resolution=${resolution}`
    ),

  intradayBacktest: (assetId: string, resolution = "15") =>
    fetchJson<IntradayBacktest>(
      `${_activeBase}/assets/${assetId}/intraday/backtest?resolution=${resolution}`
    ),

  intradayBacktestRun: (assetId: string, resolution = "15", lookbackDays = 30) =>
    postJson<IntradayBacktest>(
      `${_activeBase}/assets/${assetId}/intraday/backtest/run?resolution=${resolution}&lookback_days=${lookbackDays}`
    ),

  intradayAIAnalysis: (assetId: string, resolution = "15") =>
    postJson<IntradayAIAnalysis>(
      `${_activeBase}/assets/${assetId}/intraday/ai-analysis?resolution=${resolution}`
    ),

  simulatorPerformance: (assetId: string) =>
    fetchJson<SimulatorPerformance>(`${_activeBase}/assets/${assetId}/simulator/performance`),

  createPaperAccount: (name: string, initialCash: number, currency: string) =>
    postJson<PaperAccount>(`${_activeBase}/paper/accounts`, {
      name,
      initial_cash: initialCash,
      currency,
    }),

  paperAccount: (accountId: number) =>
    fetchJson<PaperAccount>(`${_activeBase}/paper/accounts/${accountId}`),

  placePaperOrder: (
    accountId: number,
    assetId: string,
    side: "buy" | "sell",
    quantity: number,
  ) => postJson<PaperOrder>(`${_activeBase}/paper/accounts/${accountId}/orders`, {
    asset_id: assetId,
    side,
    quantity,
  }),

  paperJournal: (accountId: number, limit = 200) =>
    fetchJson<PaperJournal>(`${_activeBase}/paper/accounts/${accountId}/journal?limit=${limit}`),

  intradaySync: (assetId: string, resolution = "15") =>
    postJson<{ asset_id: string; resolution: string; new_candles: number; fetched_from_api: number; already_in_db: number }>(
      `${_activeBase}/assets/${assetId}/intraday/sync?resolution=${resolution}`
    ),

  smsAlertConfig: () =>
    fetchJson<SmsAlertConfig>(`${_activeBase}/admin/sms-alert-config`),

  saveSmsAlertConfig: (cfg: Partial<Omit<SmsAlertConfig, "sms_status" | "alert_rule_labels" | "alert_rule_descriptions" | "threshold_labels" | "defaults">>) =>
    postJson<{ ok: boolean; saved: string[] }>(`${_activeBase}/admin/sms-alert-config`, cfg),

  anomalyScore: (assetId: string) =>
    fetchJson<AnomalyScore>(`${_activeBase}/assets/${assetId}/anomaly`),

  anomalyHistory: (assetId: string, limit = 30) =>
    fetchJson<AnomalyHistoryPoint[]>(`${_activeBase}/assets/${assetId}/anomaly/history?limit=${limit}`),

  anomalyRefresh: (assetId: string) =>
    postJson<AnomalyScore>(`${_activeBase}/assets/${assetId}/anomaly/refresh`),

  insiderSentiment: (assetId: string, days = 90) =>
    fetchJson<InsiderSentiment>(`${_activeBase}/assets/${assetId}/insider-sentiment?days=${days}`),

  syncInsider: (assetId: string) =>
    postJson<{ asset_id: string; insider_trades: number; short_interest: number }>(
      `${_activeBase}/assets/${assetId}/sync/insider`
    ),

  pead: (assetId: string) =>
    fetchJson<PEADAnalysis>(`${_activeBase}/assets/${assetId}/pead`),
};
