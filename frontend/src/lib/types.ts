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
};

export type MLStatus = {
  ml_mode: string;
  ml_enabled: boolean;
  active_model_name?: string | null;
  active_target_name?: string | null;
  dataset_rows: number;
  min_training_rows: number;
  ready_for_training: boolean;
  targets: MLActiveModel[];
};

export type MLDatasetStats = {
  total_rows: number;
  assets: Record<string, number>;
  labeled_rows_1d: number;
  labeled_rows_5d: number;
  labeled_rows_20d: number;
  thesis_success_rows: number;
};

export type MLModelRun = {
  id: number;
  model_name: string;
  target_name: string;
  trained_at: string;
  dataset_rows: number;
  metrics_json: string;
  model_path: string;
  is_active: boolean;
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
  recommendation: "KUP" | "SPRZEDAJ" | "TRZYMAJ";
  composite_score: number;
  confidence: number;
  confidence_label: string;
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
  directional_accuracy: number | null;
  active_alerts: number;
  has_critical_alert: boolean;
  rationale: string;
  top_signals: SignalContribution[];
  snapshot_at: string | null;
  data_complete: boolean;
};

export type PriceQuality    = { total_points: number; last_timestamp: string | null; staleness_hours: number | null; is_stale: boolean; gap_count: number; gap_pct: number; score: number; };
export type NewsQuality     = { total_items: number; items_7d: number; items_30d: number; last_timestamp: string | null; staleness_hours: number | null; is_stale: boolean; nlp_enriched: number; nlp_coverage_pct: number; score: number; };
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
  action: string; rationale: string;
};
export type EnsembleLeaderboard = {
  asset_id: string; name: string; total_records: number;
  heuristic_wins: number; ml_wins: number; ensemble_wins: number; ties: number;
  heuristic_win_rate: number; ml_win_rate: number; ensemble_win_rate: number;
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
