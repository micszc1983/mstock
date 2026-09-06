export type Asset = {
  id: string;
  symbol: string;
  name: string;
  type: string;
  currency: string;          // waluta przechowywanych cen: "USD" | "PLN"
  sector?: string | null;
  price_symbol?: string | null;
  news_symbol?: string | null;
  news_term?: string | null;
  metal_price_fn?: string | null;
};

export type AssetCreate = {
  id: string;
  symbol: string;
  name: string;
  type: "stock" | "metal";
  currency?: string;         // waluta: "USD" | "PLN" (domyślnie backend inferuje z price_symbol)
  sector?: string;
  price_symbol?: string;
  news_symbol?: string;
  news_term?: string;
  metal_price_fn?: string;
};
export type StoredThesis = {
  id: number; asset_id: string; generated_at: string; source_snapshot_at: string;
  regime: string; regime_confidence: number; dominant_narrative?: string | null;
  thesis_confidence: number; fragility_score: number; divergence_score: number;
  thesis: string; anti_thesis: string; support_factors: string[]; risk_factors: string[];
  invalidation_conditions: string[]; model_name: string;
};
export type Forecast = {
  asset_id: string; horizon: string; generated_at: string; direction: string;
  up_probability: number; down_probability: number; confidence: number;
  expected_return_pct: number; expected_range_low: number; expected_range_high: number;
  model_name: string; regime_label: string;
};
export type ThesisOutcome = {
  thesis_id: number; asset_id: string; evaluated_at: string; horizon: string;
  base_price: number; realized_price: number; realized_return_pct: number;
  was_directionally_correct: boolean; outcome_label: string;
};
export type ThesisQualitySummary = {
  asset_id: string; total_outcomes: number; directional_accuracy: number;
  average_realized_return_pct: number; bullish_win_rate: number; bearish_win_rate: number; flat_rate: number;
};
export type ThesisQualityByHorizon = {
  asset_id: string; horizon: string; total_outcomes: number; directional_accuracy: number;
  average_realized_return_pct: number; bullish_win_rate: number; bearish_win_rate: number; flat_rate: number;
};
export type ForecastQualitySummary = {
  asset_id: string; horizon: string; total_forecasts: number; average_up_probability: number;
  average_down_probability: number; average_confidence: number; average_expected_return_pct: number;
};
export type NarrativePoint = { date: string; narrative_scores: Record<string, number>; };


export type AlertItem = {
  id: number;
  asset_id: string;
  created_at: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  status: string;
  trigger_value: number;
  threshold_value: number;
  snapshot_json: string;
};


export type Watchlist = {
  id: number;
  name: string;
  description?: string | null;
  is_default: boolean;
  created_at: string;
  assets: string[];
};

export type Preference = {
  id: number;
  preference_key: string;
  preference_value: string;
  updated_at: string;
};

export type CompareAssetRow = {
  asset_id: string;
  last_price: number;
  trend_score: number;
  sentiment_score: number;
  divergence_score: number;
  fragility_score: number;
  regime: string;
  dominant_narrative: string | null;
  forecast_direction_1d: string | null;
  forecast_confidence_1d: number | null;
};

export type CompareAssetsResponse = {
  asset_ids: string[];
  rows: CompareAssetRow[];
};

export type AggregateDashboardResponse = {
  asset_ids: string[];
  rows: any[];
};

export type ReportResponse = {
  asset_id?: string | null;
  watchlist_id?: number | null;
  report_type: string;
  generated_at: string;
  file_path: string;
  file_name: string;
};

export type NotificationChannel = {
  id: number;
  channel_type: string;
  target: string;
  label: string;
  is_enabled: boolean;
  created_at: string;
};

export type NotificationEvent = {
  id: number;
  channel_id: number;
  asset_id?: string | null;
  event_type: string;
  status: string;
  message: string;
  created_at: string;
};


export type MLActiveModel = {
  target_name: string;
  target_label: string;
  model_name: string | null;
  is_trained: boolean;
  dataset_rows: number;
  active_models: number;
  eligible_models: number;
  shadow_models: number;
  degraded_models: number;
  outcome_samples: number;
  min_outcome_samples: number;
  activation_state: "untrained" | "shadow" | "degraded" | "partial" | "eligible";
};

export type MLStatus = {
  ml_mode: string;
  ml_enabled: boolean;
  active_model_name?: string | null;
  active_target_name?: string | null;
  dataset_rows: number;
  min_training_rows: number;
  ready_for_training: boolean;
  activation_mode: "automatic";
  emergency_disabled: boolean;
  active_models: number;
  eligible_models: number;
  shadow_models: number;
  degraded_models: number;
  outcome_samples: number;
  min_outcome_samples: number;
  targets: MLActiveModel[];
};

export type MLDatasetStats = {
  total_rows: number;
  assets: Record<string, number>;
  labeled_rows_1d: number;
  labeled_rows_5d: number;
  labeled_rows_20d: number;
  thesis_success_rows: number;
  triple_barrier_rows: number;
  meta_label_rows: number;
  oof_meta_label_rows: number;
};

export type MLModelRun = {
  id: number;
  asset_id: string | null;
  model_name: string;
  target_name: string;
  trained_at: string;
  dataset_rows: number;
  metrics_json: string;
  model_path: string;
  is_active: boolean;
  deployment_role: "champion" | "challenger" | "candidate" | "rejected" | "archived";
  promotion_reason: string | null;
  market_segment: string | null;
};

export type MLBacktest = {
  model_run_id: number;
  created_at: string;
  result_json: string;
};

export type MLModelComparison = {
  asset_id: string;
  asset_name: string;
  model_name: string;
  target_name: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  avg_probability_up: number;
  train_rows: number;
  trained_at: string | null;
  is_global?: boolean;
  cv_accuracy_mean?: number | null;
  cv_accuracy_std?: number | null;
  cv_f1_mean?: number | null;
  cv_f1_std?: number | null;
  cv_folds?: number | null;
  optuna_best_params?: Record<string, unknown> | null;
  deployment_role?: string;
  promotion_reason?: string | null;
  holdout_avg_net_return_pct?: number | null;
  holdout_profit_factor?: number | null;
  holdout_max_drawdown_pct?: number | null;
  holdout_win_rate_pct?: number | null;
  cv_method?: string | null;
  cv_purge_sessions?: number | null;
  market_segment?: string | null;
  calibration_method?: string | null;
  calibration_ece?: number | null;
  cpcv_f1_mean?: number | null;
  cpcv_paths?: number | null;
  pbo?: number | null;
  deflated_sharpe_ratio?: number | null;
};

export type MLMonitor = {
  id: number; model_run_id: number; checked_at: string;
  asset_id: string | null; market_segment: string | null;
  feature_psi: number | null; calibration_error: number | null;
  recent_avg_net_return_pct: number | null; recent_profit_factor: number | null;
  sample_size: number; is_degraded: boolean; action: string; details_json: string;
};

export type MLPrediction = {
  asset_id: string;
  snapshot_at: string;
  model_run_id: number;
  target_name: string;
  probability_up: number;
  predicted_label: string;
  raw_json: string;
};


export type StrategyComparison = {
  asset_id: string;
  heuristic_accuracy_5d: number;
  ml_accuracy_5d: number;
  heuristic_avg_return_5d: number;
  ml_avg_return_5d: number;
  better_mode: string;
  sample_size: number;
};

export type WalkForwardBacktest = {
  model_run_id: number;
  created_at: string;
  result_json: string;
};

export type DecisionSnapshot = {
  asset_id: string;
  snapshot_at: string;
  conviction_score: number;
  risk_score: number;
  timing_score: number;
  setup_quality_score: number;
  bullish_strength: number;
  bearish_pressure: number;
  net_thesis_edge: number;
  action_label: string;
  confidence_breakdown: {
    name: string;
    contribution: number;
  }[];
  scenario_base: {
    title: string;
    summary: string;
    drivers: string[];
  };
  scenario_bull: {
    title: string;
    summary: string;
    drivers: string[];
  };
  scenario_bear: {
    title: string;
    summary: string;
    drivers: string[];
  };
  change_summary: {
    metric: string;
    previous: string;
    current: string;
    delta: string;
    interpretation: string;
  }[];
  position_sizing: {
    suggested_size_label: string;
    sizing_fraction: number;
    rationale: string;
  };
  cross_asset_confirmation: {
    related_asset: string;
    relationship: string;
    confirmation: string;
    interpretation: string;
  }[];
  regime_memory: {
    label: string;
    similarity_score: number;
    interpretation: string;
  }[];
  macro_pressure?: {
    usd_pressure: number;
    real_yield_pressure: number;
    safe_haven_demand: number;
    central_bank_buying: number;
    inflation_hedge_support: number;
    summary: string;
  } | null;
  relative_strength?: {
    ratio_name: string;
    value: number;
    interpretation: string;
  } | null;
  company_risk_stack?: {
    valuation_pressure: number;
    earnings_sensitivity: number;
    regulation_risk: number;
    competition_pressure: number;
    product_cycle_strength: number;
    summary: string;
  } | null;
};

export type MLFeatureImportance = {
  feature: string;
  importance: number;
  direction: "bullish" | "bearish";
};

export type MLPredictionContribution = {
  feature: string;
  feature_value: number;
  contribution: number;
  direction: "bullish" | "bearish";
};

export type MLExplanation = {
  asset_id: string;
  target_name: string;
  probability_up: number;
  predicted_label: string;
  interpretation: string;
  feature_importances: MLFeatureImportance[];
  prediction_contributions: MLPredictionContribution[];
};

export type SignalContribution = {
  name: string;
  value: number;
  normalized: number;
  direction: "bullish" | "bearish" | "neutral";
};

export type AssetRecommendation = {
  asset_id: string;
  name: string;
  symbol: string;
  asset_type: string;
  recommendation: "KUP" | "SPRZEDAJ" | "TRZYMAJ" | "BRAK TRANSAKCJI";
  composite_score: number;
  confidence: number;
  confidence_label: string;
  market_segment: "GPW" | "USA" | "OTHER" | "UNKNOWN";
  calibration_scope: "market_regime" | "market" | "regime" | "global" | "insufficient_data";
  calibration_sample_size: number;
  probability_buy: number;
  probability_sell: number;
  probability_no_trade: number;
  buy_threshold: number;
  sell_threshold: number;
  transaction_cost_pct: number;
  expected_gross_edge_pct: number;
  expected_net_edge_pct: number;
  uncertainty_pct: number;
  no_trade_reason: string | null;
  trend_score: number;
  sentiment_score: number;
  fragility_score: number;
  divergence_score: number;
  regime: string;
  forecast_dir_1d: string | null;
  forecast_dir_5d: string | null;
  forecast_dir_20d: string | null;
  forecast_up_1d: number | null;
  forecast_up_5d: number | null;
  forecast_up_20d: number | null;
  conviction_score: number | null;
  risk_score: number | null;
  action_label: string | null;
  ml_prediction: string | null;
  ml_prob_up: number | null;
  ml_20d_prediction: string | null;
  ml_20d_prob_up: number | null;
  ml_thesis_prediction: string | null;
  ml_meta_prediction: string | null;
  meta_trade_probability: number | null;
  meta_gate_applied: boolean;
  meta_trade_threshold: number | null;
  meta_threshold_scope: string | null;
  directional_accuracy: number | null;
  active_alerts: number;
  has_critical_alert: boolean;
  rationale: string;
  top_signals: SignalContribution[];
  snapshot_at: string | null;
  data_complete: boolean;
  implied_volatility: number | null;
  put_call_ratio: number | null;
  iv_rank: number | null;
  earnings_surprise_pct: number | null;
  last_price: number | null;
};

export type TopPick = AssetRecommendation & {
  certainty_score: number;
  signals_aligned: number;
  max_signals: number;
  aligned_labels: string[];
  missing_labels: string[];
};

export type RecommendationStrategyMetrics = {
  signals: number;
  trades: number;
  coverage_pct: number;
  no_trade_pct: number;
  win_rate_pct: number;
  avg_net_return_pct: number;
  median_net_return_pct: number;
  profit_factor: number | null;
  portfolio_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number | null;
  sortino: number | null;
};

export type RecommendationAudit = {
  id: number;
  model_version: string;
  created_at: string;
  dataset_rows: number;
  eligible_rows: number;
  evaluated_rows: number;
  excluded_outliers: number;
  outlier_reasons: Record<string, number>;
  fold_count: number;
  embargo_sessions: number;
  horizon_sessions: number;
  folds: Array<{
    fold: number; train_end_exclusive: string; test_start: string; test_end: string;
    train_rows: number; test_rows: number; embargo_sessions: number; scopes: Record<string, number>;
  }>;
  strategies: Record<string, RecommendationStrategyMetrics>;
  calibration: {
    multiclass_brier: number; log_loss: number; ece: number;
    class_accuracy_pct: number; trade_direction_accuracy_pct: number;
    bins: Array<{ from: number; to: number; count: number; accuracy: number; confidence: number }>;
  };
  by_market: Array<{ name: string } & RecommendationStrategyMetrics>;
  by_regime: Array<{ name: string } & RecommendationStrategyMetrics>;
  notes: string[];
};

export type RecommendationJournalRecord = {
  id: number; asset_id: string; snapshot_at: string; created_at: string;
  model_version: string; revision: number; previous_record_id: number | null;
  change_type: "initial" | "legacy" | "action" | "position" | "data_quality" | "calibration" | "signals";
  change_summary: string | null; change_details_json: string; signal_snapshot_json: string;
  market: string; regime: string; action: string;
  displayed_action: string; has_position: boolean; calibration_scope: string;
  calibration_sample_size: number; composite_score: number; confidence: number;
  probability_buy: number; probability_sell: number; probability_no_trade: number;
  buy_threshold: number; sell_threshold: number; transaction_cost_pct: number;
  expected_gross_edge_pct: number; expected_net_edge_pct: number; uncertainty_pct: number;
  base_price: number | null; quality_flag: string | null;
  realized_return_1d_pct: number | null; realized_return_5d_pct: number | null;
  realized_return_20d_pct: number | null; strategy_net_return_1d_pct: number | null;
  strategy_net_return_5d_pct: number | null; strategy_net_return_20d_pct: number | null;
  evaluated_at: string | null;
  meta_trade_probability: number | null; meta_gate_applied: boolean;
  meta_trade_threshold: number | null; meta_threshold_scope: string | null;
  no_trade_reason: string | null; rationale: string | null; data_complete: boolean;
};

export type EarningsRecord = {
  id: number;
  asset_id: string;
  report_date: string;          // ISO date "2025-01-28"
  fiscal_period: string | null; // "2025Q1"
  eps_estimate: number | null;
  eps_actual: number | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  eps_surprise_pct: number | null;
  surprise_label: "BEAT" | "MISS" | "MEET" | null;
  is_upcoming: boolean;
  created_at: string;
  updated_at: string;
};

export type EarningsCalendarEntry = {
  asset_id: string;
  symbol: string;
  name: string;
  report_date: string;
  fiscal_period: string | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  eps_surprise_pct: number | null;
  surprise_label: "BEAT" | "MISS" | "MEET" | null;
  is_upcoming: boolean;
};

export type EarningsCalendarResponse = {
  upcoming: EarningsCalendarEntry[];
  recent: EarningsCalendarEntry[];
};

export type EarningsCallAnalysis = {
  id: number;
  earnings_id: number;
  asset_id: string;
  analyzed_at: string;
  tone_score: number;            // 1–5
  guidance_change: string;       // raised | lowered | maintained | none
  key_themes: string[];
  risk_factors: string[];
  key_quote: string | null;
  llm_sentiment_score: number;   // -100 do +100
  summary: string;
  model_used: string;
  news_articles_used: number;
};

export type PriceQuality    = { total_points: number; last_timestamp: string | null; staleness_hours: number | null; is_stale: boolean; gap_count: number; gap_pct: number; score: number; };
export type NewsQuality     = { total_items: number; items_7d: number; items_30d: number; last_timestamp: string | null; staleness_hours: number | null; is_stale: boolean; nlp_enriched: number; nlp_coverage_pct: number; nlp_model: string; current_model_items_30d: number; current_model_coverage_30d_pct: number; relevant_items_7d: number; relevance_mean_7d: number; low_relevance_pct_7d: number; source_count_7d: number; score: number; };
export type FeatureQuality  = { has_snapshot: boolean; staleness_hours: number | null; is_stale: boolean; scores_nonzero: boolean; has_all_forecasts: boolean; has_decision_snapshot: boolean; score: number; };
export type MLQuality       = { training_rows: number; labeled_rows_5d: number; labeled_rows_20d: number; labeled_rows_thesis: number; label_coverage_pct: number; min_required: number; ready_for_training: boolean; score: number; };
export type SyncQuality     = { errors_24h: number; errors_7d: number; total_syncs_7d: number; error_rate_7d: number; last_successful_sync: string | null; last_error: string | null; score: number; };

export type AssetDataQuality = {
  asset_id: string; name: string; symbol: string; asset_type: string;
  prices: PriceQuality; news: NewsQuality; features: FeatureQuality;
  ml: MLQuality; sync: SyncQuality;
  overall_score: number; grade: string; grade_label: string;
  issues: string[]; warnings: string[]; checked_at: string;
};

export type DataQualityReport = {
  assets: AssetDataQuality[];
  checked_at: string;
  summary: Record<string, number | Record<string, number>>;
};

export type SignalVote = {
  source: string; source_label: string; direction: string;
  confidence: number; probability_up: number; reasoning: string; available: boolean;
};
export type EnsembleSignal = {
  asset_id: string; snapshot_at: string; mode: string; mode_label: string;
  votes: SignalVote[];
  final_direction: string; final_confidence: number; final_probability_up: number;
  consensus: string; consensus_score: number;
  heuristic_weight: number; ml_weight: number;
  weights_dynamic: boolean;
  weights_method: string;
  weights_evaluated_records: number;
  action: string; rationale: string;
};

export type DynamicWeightInfo = {
  asset_id: string;
  heuristic_weight: number;
  ml_weight: number;
  is_dynamic: boolean;
  evaluated_records: number;
  heuristic_accuracy: number;
  ml_accuracy: number;
  method: string;
  min_records_required: number;
};
export type EnsembleLeaderboard = {
  asset_id: string; name: string; total_records: number; evaluated_records: number;
  heuristic_accuracy: number; ml_accuracy: number; ensemble_accuracy: number;
  recommended_mode: string;
  avg_heuristic_confidence: number; avg_ml_confidence: number;
  last_updated: string | null;
};

export type PriceBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type InsiderTrade = {
  id: number;
  asset_id: string;
  transaction_date: string;
  filing_date: string | null;
  name: string;
  transaction_code: string;
  transaction_type: "buy" | "sell" | "other";
  shares: number | null;
  price: number | null;
  value: number | null;
  source: string;
  created_at: string;
};

export type ShortInterest = {
  id: number;
  asset_id: string;
  report_date: string;
  shares_short: number | null;
  short_percent_float: number | null;
  short_ratio: number | null;
  created_at: string;
};

export type AlertRuleConfig = {
  enabled: boolean;
  threshold?: number;
  cooldown_minutes: number;
};

export type SmsAlertConfig = {
  sms_status: {
    enabled: boolean;
    port: string;
    recipient: string;
    finnhub_configured: boolean;
  };
  alert_rules: Record<string, AlertRuleConfig>;
  top_picks_sms: { enabled: boolean };
  paper_trading_sms: { enabled: boolean };
  portfolio_sell_urgent: { enabled: boolean; cooldown_minutes: number };
  premarket_gap: {
    enabled: boolean;
    portfolio_threshold_pct: number;
    watchlist_threshold_pct: number;
  };
  alert_rule_labels: Record<string, string>;
  alert_rule_descriptions: Record<string, string>;
  threshold_labels: Record<string, string>;
  defaults: Record<string, unknown>;
};

export type IntradayCandle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  rsi: number | null;
  ema9: number | null;
  ema20: number | null;
  macd: number | null;
  macd_signal: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  volume_ratio: number | null;
  vwap: number | null;
};

export type SwingSignal = {
  type: "BUY" | "SELL";
  timestamp: string;
  price: number;
  strength: number;
  reasons: string[];
  rsi: number | null;
  volume_ratio: number | null;
  vwap: number | null;
};

export type RSDataPoint = {
  timestamp: string;
  rs: number;
  asset_ret: number;
  bench_ret: number;
};

export type RelativeStrengthData = {
  data: RSDataPoint[];
  benchmark: string;
  current_rs: number | null;
};

export type VPBin = {
  price: number;
  volume: number;
  pct: number;
  is_poc: boolean;
  in_va: boolean;
};

export type VolumeProfile = {
  poc: number;
  vah: number;
  val: number;
  price_low: number;
  price_high: number;
  total_volume: number;
  bins: VPBin[];
};

export type OpeningRange = {
  high: number;
  low: number;
  breakout_up: boolean;
  breakout_down: boolean;
  range_pct: number;
};

export type CandlePattern = {
  name: string;
  type: "bullish" | "bearish" | "neutral";
  timestamp: string;
  price: number;
  description: string;
  strength: number;
};

export type InsiderTradeEntry = {
  date: string;
  name: string;
  type: "buy" | "sell" | "other";
  code: string;
  shares: number | null;
  price: number | null;
  value: number | null;
};

export type InsiderSentiment = {
  asset_id: string;
  days: number;
  signal: "bullish" | "bearish" | "neutral";
  signal_description: string;
  n_buys: number;
  n_sells: number;
  buy_shares: number;
  sell_shares: number;
  net_shares: number;
  buy_value: number;
  sell_value: number;
  recent_trades: InsiderTradeEntry[];
};

export type AnomalyFeature = {
  feature: string;
  value: number;
  median: number;
  z_score: number;
};

export type AnomalyScore = {
  asset_id: string;
  scored_at: string;
  anomaly_score: number;   // 0-100, 100 = najbardziej anomalny
  is_anomaly: boolean;
  trained_on_rows: number;
  top_features: AnomalyFeature[];
};

export type AnomalyHistoryPoint = {
  scored_at: string;
  anomaly_score: number;
  is_anomaly: boolean;
};

export type MarketRegime = {
  regime: "trend_up" | "trend_down" | "range" | "volatile" | "unknown";
  adx: number | null;
  di_plus: number | null;
  di_minus: number | null;
  bb_squeeze: boolean;
  description: string;
};

export type PEADEvent = {
  report_date: string;
  fiscal_period: string | null;
  eps_surprise_pct: number | null;
  surprise_label: "BEAT" | "MISS" | "MEET" | null;
  drift_1d: number | null;
  drift_5d: number | null;
  drift_20d: number | null;
  aligned: boolean | null;
};

export type PEADAnalysis = {
  asset_id: string;
  status: "active" | "expired" | "no_data";
  status_description: string;
  reliability_pct: number | null;
  n_events: number;
  events: PEADEvent[];
  current_drift_pct: number | null;
  days_since_earnings: number | null;
  last_report_date: string | null;
  last_surprise_label: "BEAT" | "MISS" | "MEET" | null;
  last_eps_surprise_pct: number | null;
  sue: number | null;
};

export type IntradayBacktestTrade = {
  direction: "BUY" | "SELL";
  entry_price: number;
  pct: number;
  result: "TP" | "SL" | "TIMEOUT";
  bars_held: number;
  timestamp: string;
};

export type IntradayBacktest = {
  id: number;
  asset_id: string;
  resolution: string;
  run_at: string;
  lookback_days: number;
  candles_count: number;
  total_signals: number;
  win_count: number;
  loss_count: number;
  timeout_count: number;
  win_rate: number | null;
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  avg_return_pct: number | null;
  total_return_pct: number | null;
  expectancy: number | null;
  calibrated: {
    rsi_oversold: number;
    rsi_overbought: number;
    sl_pct: number;
    tp_pct: number;
  };
  default: {
    total_signals: number;
    win_rate: number | null;
    expectancy: number | null;
  };
  trades: IntradayBacktestTrade[];
  portfolio: {
    initial_capital?: number;
    final_capital?: number;
    net_profit?: number;
    return_pct?: number;
    max_drawdown_pct?: number;
    sharpe?: number;
    sortino?: number;
    profit_factor?: number | null;
    total_costs?: number;
    commission_pct?: number;
    slippage_pct?: number;
  };
};

export type IntradayAIAnalysis = {
  decyzja: "KUP" | "TRZYMAJ" | "SPRZEDAJ";
  pewnosc: number;
  uzasadnienie: string;
  kluczowe_argumenty: string[];
  ryzyka: string[];
  poziomy: {
    wejscie: number | null;
    stop_loss: number | null;
    take_profit: number | null;
  };
  horyzont: string;
  _model?: string;
  _cached?: boolean;
};

export type IntradayFullResponse = {
  candles: IntradayCandle[];
  signals: IntradaySignalsResponse;
  volume_profile: VolumeProfile | null;
  relative_strength: RelativeStrengthData | null;
  anomaly: AnomalyScore | null;
  insider: InsiderSentiment | null;
  pead: PEADAnalysis | null;
};

export type IntradaySignalsResponse = {
  signals: SwingSignal[];
  patterns: CandlePattern[];
  support: number[];
  resistance: number[];
  candles_count: number;
  opening_range: OpeningRange | Record<string, never>;
  current_vwap: number | null;
  regime: MarketRegime;
};

export type SimulatorReturnPeriod = {
  key: "1w" | "1m" | "3m" | "1y";
  label: string;
  days: number;
  start_price: number | null;
  end_price: number;
  return_pct: number | null;
  available: boolean;
};

export type SimulatorPerformance = {
  asset_id: string;
  symbol: string;
  name: string;
  currency: string;
  current_price: number | null;
  last_price_date: string | null;
  returns: SimulatorReturnPeriod[];
  has_enough_data: boolean;
};

export type PaperPosition = {
  asset_id: string;
  quantity: number;
  avg_price: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
};

export type PaperAccount = {
  id: number;
  name: string;
  currency: string;
  initial_cash: number;
  cash: number;
  market_value: number;
  equity: number;
  total_return_pct: number;
  unrealized_pnl: number;
  positions: PaperPosition[];
  strategy: PaperStrategy | null;
};

export type PaperStrategyBucket = {
  id: number;
  ordinal: number;
  initial_amount: number;
  cash: number;
  asset_id: string | null;
  quantity: number;
  avg_price: number;
  last_price: number | null;
  value: number;
  return_pct: number;
  status: "waiting" | "position";
  signal_status: "waiting" | "confirming" | "entry_active" | "entry_expired" | "exit_signal";
  signal_message: string;
  current_recommendation: string | null;
  pending_asset_id: string | null;
  pending_signal_count: number;
  pending_since: string | null;
  opened_at: string | null;
  updated_at: string;
};

export type PaperStrategy = {
  id: number;
  active: boolean;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  last_message: string;
  buckets: PaperStrategyBucket[];
};

export type PaperOrder = {
  id: number;
  account_id: number;
  asset_id: string;
  side: "buy" | "sell";
  order_type: "market";
  quantity: number;
  status: "submitted" | "filled" | "rejected";
  submitted_at: string;
  filled_at: string | null;
  reference_price: number;
  fill_price: number | null;
  commission: number;
  slippage: number;
  note: string;
};

export type PaperTrade = {
  id: number;
  order_id: number;
  account_id: number;
  asset_id: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  gross_value: number;
  costs: number;
  realized_pnl: number;
  executed_at: string;
};

export type PaperJournal = { orders: PaperOrder[]; trades: PaperTrade[] };

export type PaperAllocation = {
  amount: number;
  asset_id: string;
  symbol: string;
  name: string;
  quantity: number;
  reference_price: number;
  fill_price: number;
  invested_amount: number;
  entry_costs: number;
  confidence: number;
  expected_net_edge_pct: number;
  uncertainty_pct: number;
  market_segment: string;
  regime: string;
  order_id: number;
};

export type PaperAllocationResponse = {
  requested_amounts: number[];
  allocations: PaperAllocation[];
  unallocated: { amount: number; reason: string }[];
  account: PaperAccount;
};
