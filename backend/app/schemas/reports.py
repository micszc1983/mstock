from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class ReportResponse(BaseModel):
    asset_id: str | None = None
    watchlist_id: int | None = None
    report_type: str
    generated_at: datetime
    file_path: str
    file_name: str
