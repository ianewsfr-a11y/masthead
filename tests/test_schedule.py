"""Scheduled runs: next run time, pause switch, one run at a time, and the API."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from masthead.domains import create_from_template
from masthead.schedule import ScheduleError, Scheduler, next_run, parse_schedule
from masthead.server import create_app

UTC = timezone.utc
PARIS = {"time": "07:00", "timezone": "Europe/Paris", "enabled": True}


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_next_run_is_today_or_tomorrow_in_the_domains_time_zone():
    schedule = parse_schedule(PARIS)
    assert next_run(schedule, at("2026-11-14T05:00:00")) == at("2026-11-14T06:00:00")  # 07:00 in Paris, winter
    assert next_run(schedule, at("2026-11-14T06:00:00")) == at("2026-11-15T06:00:00")  # exactly now: tomorrow
    assert next_run(schedule, at("2026-11-14T06:30:00")) == at("2026-11-15T06:00:00")


def test_next_run_follows_daylight_saving_time():
    schedule = parse_schedule(PARIS)
    # Paris moves to summer time on 28 March 2027: 07:00 becomes 05:00 UTC.
    assert next_run(schedule, at("2027-03-27T07:00:00")) == at("2027-03-28T05:00:00")


@pytest.mark.parametrize("bad", [
    {"time": "25:00", "timezone": "Europe/Paris"},
    {"time": "7h", "timezone": "Europe/Paris"},
    {"time": "07:00", "timezone": "Mars/Olympus"},
    {"time": "07:00", "timezone": "Europe/Paris", "enabled": "yes"},
    "07:00",
])
def test_invalid_schedules_are_refused(bad):
    with pytest.raises(ScheduleError):
        parse_schedule(bad)


def test_paused_schedule_has_no_next_run():
    assert next_run(parse_schedule({**PARIS, "enabled": False}), at("2026-11-14T05:00:00")) is None


class FakeRuns:
    def __init__(self, busy=False):
        self.busy = busy
        self.started: list[str] = []

    def start(self, domain_id: str) -> dict:
        if self.busy:
            raise RuntimeError("A run is already in progress.")
        self.started.append(domain_id)
        return {"id": "job1", "run_id": None}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def _scheduled(domain_id: str, schedule: dict):
    domain = create_from_template(domain_id)
    meta = domain.meta()
    meta["schedule"] = schedule
    domain.write_meta(meta)
    return domain


async def test_a_due_run_starts_once_and_the_result_is_kept(home):
    _scheduled("flight-sim", PARIS)
    runs = FakeRuns()
    scheduler = Scheduler(start_run=runs.start)
    await scheduler.tick(at("2026-11-14T05:00:00"))  # first look: due at 06:00
    assert runs.started == []
    await scheduler.tick(at("2026-11-14T06:00:30"))
    await scheduler.tick(at("2026-11-14T06:01:00"))
    assert runs.started == ["flight-sim"]
    state = scheduler.status("flight-sim", at("2026-11-14T06:01:00"))
    assert state["last"]["outcome"] == "started" and state["last"]["job_id"] == "job1"
    assert state["next_run"] == at("2026-11-15T06:00:00").isoformat()


async def test_a_due_run_is_skipped_while_another_run_is_in_progress(home):
    _scheduled("flight-sim", PARIS)
    runs = FakeRuns(busy=True)
    scheduler = Scheduler(start_run=runs.start)
    await scheduler.tick(at("2026-11-14T05:00:00"))
    await scheduler.tick(at("2026-11-14T06:00:30"))
    last = scheduler.status("flight-sim", at("2026-11-14T06:01:00"))["last"]
    assert last["outcome"] == "skipped" and "already in progress" in last["message"]


async def test_a_paused_domain_does_not_run(home):
    _scheduled("flight-sim", {**PARIS, "enabled": False})
    runs = FakeRuns()
    scheduler = Scheduler(start_run=runs.start)
    await scheduler.tick(at("2026-11-14T05:00:00"))
    await scheduler.tick(at("2026-11-14T06:00:30"))
    assert runs.started == []
    assert scheduler.status("flight-sim", at("2026-11-14T06:01:00"))["next_run"] is None


def test_schedule_api_sets_pauses_and_validates(home):
    create_from_template("flight-sim")
    with TestClient(create_app(), headers={"host": "127.0.0.1:8765"}) as client:
        assert client.get("/api/domains/flight-sim").json()["schedule"]["configured"] is False

        saved = client.post("/api/domains/flight-sim/schedule", json=PARIS)
        assert saved.status_code == 200
        schedule = saved.json()["schedule"]
        assert schedule["configured"] and schedule["enabled"] and schedule["next_run"]

        paused = client.post("/api/domains/flight-sim/schedule", json={**PARIS, "enabled": False}).json()["schedule"]
        assert paused["enabled"] is False and paused["next_run"] is None

        assert client.post("/api/domains/flight-sim/schedule",
                           json={"time": "99:00", "timezone": "Europe/Paris"}).status_code == 400
        removed = client.post("/api/domains/flight-sim/schedule", json={"remove": True}).json()["schedule"]
        assert removed["configured"] is False
