from __future__ import annotations

import os
from typing import Dict, List, Optional

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        app_name: str = "MStock"
        app_version: str = "0.4.0"
        database_url: str = "sqlite:///./mstock.db"
        alphavantage_api_key: str = ""
        finnhub_api_key: str = ""
        newsapi_api_key: str = ""
        massive_api_key: str = ""
        twelvedata_api_key: str = ""
        rapidapi_api_key: str = ""
        anthropic_api_key: str = ""
        sync_timeout_seconds: float = 20.0
        auto_sync_enabled: bool = True
        auto_sync_interval_minutes: int = 60
        smtp_host: str = ""
        smtp_port: int = 587
        smtp_username: str = ""
        smtp_password: str = ""
        smtp_from_email: str = ""
        report_recipient_email: str = ""
        twilio_account_sid: str = ""
        twilio_auth_token: str = ""
        twilio_whatsapp_from: str = ""
        reports_dir: str = "./generated_reports"
        ml_enabled_default: bool = False
        ml_models_dir: str = "./ml_models"
        ml_min_training_rows: int = 120
        # CORS — jako str żeby pydantic-settings nie próbował parsować jako JSON
        # Wartość w .env: http://localhost:5173,http://127.0.0.1:5173
        cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
        # Scheduler — dodatkowe opcje
        reports_auto_enabled: bool = False
        notifications_auto_enabled: bool = False
        ml_retrain_auto_enabled: bool = True

        # SMS via SIM800C (USB modem, AT commands)
        sms_enabled: bool = False
        sms_serial_port: str = "/dev/ttyUSB0"   # port USB modemu (ls /dev/ttyUSB*)
        sms_baud_rate: int = 9600
        sms_recipient_phone: str = ""            # format: +48XXXXXXXXX
        sms_data_quality_threshold: float = 40.0 # próg overall_score (0-100) poniżej którego alert

        @property
        def cors_origins_list(self) -> List[str]:
            """Parsuje cors_origins (string z przecinkami) na listę."""
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        @property
        def asset_provider_config(self) -> Dict[str, Dict[str, Optional[str]]]:
            from app.asset_registry import PROVIDER_CONFIG
            return PROVIDER_CONFIG

except ImportError:
    from dataclasses import dataclass, field

    @dataclass(slots=True)
    class Settings:  # type: ignore[no-redef]
        app_name: str = "MStock"
        app_version: str = "0.4.0"
        database_url: str = os.getenv("DATABASE_URL", "sqlite:///./mstock.db")
        alphavantage_api_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
        finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
        newsapi_api_key: str = os.getenv("NEWSAPI_API_KEY", "")
        massive_api_key: str = os.getenv("MASSIVE_API_KEY", "")
        twelvedata_api_key: str = os.getenv("TWELVEDATA_API_KEY", "")
        rapidapi_api_key: str = os.getenv("RAPIDAPI_API_KEY", "")
        anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        sync_timeout_seconds: float = float(os.getenv("SYNC_TIMEOUT_SECONDS", "20"))
        auto_sync_enabled: bool = os.getenv("AUTO_SYNC_ENABLED", "true").lower() == "true"
        auto_sync_interval_minutes: int = int(os.getenv("AUTO_SYNC_INTERVAL_MINUTES", "60"))
        smtp_host: str = os.getenv("SMTP_HOST", "")
        smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        smtp_username: str = os.getenv("SMTP_USERNAME", "")
        smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")
        report_recipient_email: str = os.getenv("REPORT_RECIPIENT_EMAIL", "")
        twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        twilio_whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "")
        reports_dir: str = os.getenv("REPORTS_DIR", "./generated_reports")
        ml_enabled_default: bool = os.getenv("ML_ENABLED_DEFAULT", "false").lower() == "true"
        ml_models_dir: str = os.getenv("ML_MODELS_DIR", "./ml_models")
        ml_min_training_rows: int = int(os.getenv("ML_MIN_TRAINING_ROWS", "120"))
        reports_auto_enabled: bool = os.getenv("REPORTS_AUTO_ENABLED", "false").lower() == "true"
        notifications_auto_enabled: bool = os.getenv("NOTIFICATIONS_AUTO_ENABLED", "false").lower() == "true"
        ml_retrain_auto_enabled: bool = os.getenv("ML_RETRAIN_AUTO_ENABLED", "true").lower() == "true"
        sms_enabled: bool = os.getenv("SMS_ENABLED", "false").lower() == "true"
        sms_serial_port: str = os.getenv("SMS_SERIAL_PORT", "/dev/ttyUSB0")
        sms_baud_rate: int = int(os.getenv("SMS_BAUD_RATE", "9600"))
        sms_recipient_phone: str = os.getenv("SMS_RECIPIENT_PHONE", "")
        sms_data_quality_threshold: float = float(os.getenv("SMS_DATA_QUALITY_THRESHOLD", "40.0"))
        cors_origins: list = field(
            default_factory=lambda: os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
        )
        @property
        def asset_provider_config(self) -> Dict[str, Dict[str, Optional[str]]]:
            from app.asset_registry import PROVIDER_CONFIG
            return PROVIDER_CONFIG


settings = Settings()


# ---------------------------------------------------------------------------
# Wagi heurystyk — zebrane w jednym miejscu zamiast magic numbers w kodzie.
# Zmiana tutaj wpływa na analytics.py, decision_support.py i forecasting.py.
# ---------------------------------------------------------------------------
class HeuristicWeights:
    # Trend score
    TREND_EMA_ABOVE_20_W: float = 30.0
    TREND_EMA5_VS_EMA20_W: float = 20.0
    TREND_RET5_SCALE: float = 2.0
    TREND_RET20_CLAMP: float = 30.0

    # Fragility
    FRAGILITY_SHIFT_W: float = 0.45
    FRAGILITY_DIVERGENCE_W: float = 0.40
    FRAGILITY_SENTIMENT_W: float = 0.15

    # Thesis confidence
    THESIS_TREND_W: float = 0.35
    THESIS_SENTIMENT_W: float = 0.25
    THESIS_DIVERGENCE_W: float = 0.20
    THESIS_FRAGILITY_W: float = 0.20

    # Decision support — conviction
    CONVICTION_TREND_W: float = 0.40
    CONVICTION_SENTIMENT_W: float = 0.25
    CONVICTION_FORECAST_W: float = 0.35
    RISK_FRAGILITY_W: float = 0.60
    RISK_DIVERGENCE_W: float = 0.40

    # Forecast base signal
    FORECAST_TREND_W: float = 0.40
    FORECAST_SENTIMENT_W: float = 0.20
    FORECAST_MOMENTUM_W: float = 0.15
    FORECAST_DIVERGENCE_PENALTY: float = 0.15
    FORECAST_FRAGILITY_PENALTY: float = 0.10
    FORECAST_RETURN_SCALE: float = 4.5


weights = HeuristicWeights()
