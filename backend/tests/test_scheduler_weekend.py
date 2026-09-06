from datetime import datetime, timezone

from app.services import scheduler as scheduler_module


def test_warsaw_weekend_boundary_and_weekday_wrapper(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler_module, "run_periodic_sync", lambda: calls.append("full"))

    saturday = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)

    assert scheduler_module._is_warsaw_weekend(saturday) is True
    assert scheduler_module._weekday_periodic_sync_job(saturday) is False
    assert calls == []

    assert scheduler_module._is_warsaw_weekend(monday) is False
    assert scheduler_module._weekday_periodic_sync_job(monday) is True
    assert calls == ["full"]


def test_scheduler_registers_separate_weekend_and_sunday_jobs(monkeypatch):
    class FakeScheduler:
        running = False

        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

        def start(self):
            self.running = True

    fake = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", fake)
    monkeypatch.setattr(scheduler_module.settings, "auto_sync_enabled", True)
    monkeypatch.setattr(scheduler_module.settings, "weekend_news_interval_hours", 3)
    monkeypatch.setattr(scheduler_module.settings, "sunday_prepare_hour", 21)

    scheduler_module.start_scheduler()

    jobs = {kwargs["id"]: (func, trigger, kwargs) for func, trigger, kwargs in fake.jobs}
    assert jobs["full-pipeline"][0] is scheduler_module._weekday_periodic_sync_job
    assert jobs["weekend-news"][0] is scheduler_module.run_weekend_news_sync
    assert jobs["weekend-news"][1] == "cron"
    assert jobs["weekend-news"][2]["day_of_week"] == "sat,sun"
    assert jobs["weekend-news"][2]["hour"] == "*/3"
    assert jobs["sunday-prepare"][0] is scheduler_module.run_periodic_sync
    assert jobs["sunday-prepare"][2]["day_of_week"] == "sun"
    assert jobs["sunday-prepare"][2]["hour"] == 21
    assert jobs["sunday-prepare"][2]["minute"] == 30

