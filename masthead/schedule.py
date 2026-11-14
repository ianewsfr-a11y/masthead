"""Scheduled runs: one full run per day per domain, at a local time in a time zone.

The schedule lives in the domain's domain.json:

    "schedule": {"time": "07:00", "timezone": "Europe/Paris", "enabled": true}

"enabled": false pauses it. A run that falls due while another run is in
progress is skipped, not queued (one run at a time). Runs missed while
MastHead was stopped are not caught up. The last scheduled outcome is kept in
the domain's data/masthead_schedule.json, so it survives a restart.
"""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .domains import Domain, list_domains

STATE_FILE = "masthead_schedule.json"
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    """A schedule that cannot be used."""


@dataclass(frozen=True)
class Schedule:
    at: time
    zone: str
    enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {"time": self.at.strftime("%H:%M"), "timezone": self.zone, "enabled": self.enabled}


def parse_schedule(value: Any) -> Schedule:
    if not isinstance(value, dict):
        raise ScheduleError("A schedule needs a time and a time zone.")
    match = _TIME.fullmatch(str(value.get("time", "")))
    if not match:
        raise ScheduleError("Give the time as HH:MM, from 00:00 to 23:59.")
    zone = value.get("timezone")
    try:
        ZoneInfo(str(zone))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduleError(f"Unknown time zone: {zone}.") from exc
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ScheduleError("'enabled' must be true or false.")
    return Schedule(at=time(int(match.group(1)), int(match.group(2))), zone=str(zone), enabled=enabled)


def next_run(schedule: Schedule, now: datetime) -> datetime | None:
    """The next moment, strictly after now, when the schedule falls due (in UTC)."""
    if not schedule.enabled:
        return None
    zone = ZoneInfo(schedule.zone)
    day = now.astimezone(zone).date()
    for offset in range(3):
        local = datetime.combine(day + timedelta(days=offset), schedule.at, tzinfo=zone)
        due = local.astimezone(timezone.utc)
        if due > now:
            return due
    raise AssertionError("unreachable: a day later is always in the future")


def schedule_of(domain: Domain) -> Schedule | None:
    value = domain.meta().get("schedule")
    if value is None:
        return None
    try:
        return parse_schedule(value)
    except ScheduleError:
        return None  # an invalid hand edit never starts a run; the API reports it


def _state_path(domain: Domain):
    return domain.path / "data" / STATE_FILE


def read_state(domain: Domain) -> dict[str, Any] | None:
    try:
        value = json.loads(_state_path(domain).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_state(domain: Domain, state: dict[str, Any]) -> None:
    path = _state_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class Scheduler:
    """Checks every domain's schedule and starts the runs that fall due."""

    def __init__(self, start_run: Callable[[str], dict[str, Any]], interval_seconds: float = 30) -> None:
        self._start_run = start_run
        self.interval = interval_seconds
        self._due: dict[str, tuple[Schedule, datetime | None]] = {}

    def forget(self, domain_id: str) -> None:
        """Recompute this domain's next run at the next check (its schedule changed)."""
        self._due.pop(domain_id, None)

    async def tick(self, now: datetime) -> None:
        for domain in list_domains():
            schedule = schedule_of(domain)
            if schedule is None:
                self._due.pop(domain.id, None)
                continue
            known = self._due.get(domain.id)
            if known is None or known[0] != schedule:
                self._due[domain.id] = (schedule, next_run(schedule, now))
                continue
            due = known[1]
            if due is None or now < due:
                continue
            self._due[domain.id] = (schedule, next_run(schedule, now))
            self._launch(domain, due)

    def _launch(self, domain: Domain, due: datetime) -> None:
        state: dict[str, Any] = {"due": due.isoformat(), "at": datetime.now(timezone.utc).isoformat()}
        try:
            job = self._start_run(domain.id)
            state.update(outcome="started", job_id=job.get("id"), message=None)
        except RuntimeError as exc:  # another run is in progress
            state.update(outcome="skipped", job_id=None, message=str(exc))
        except Exception as exc:  # the reason is shown to the user; the trace goes to the terminal
            traceback.print_exc()
            state.update(outcome="failed_to_start", job_id=None, message=str(exc) or exc.__class__.__name__)
        write_state(domain, state)

    def status(self, domain_id: str, now: datetime) -> dict[str, Any]:
        from .domains import get_domain

        domain = get_domain(domain_id)
        raw = domain.meta().get("schedule")
        result: dict[str, Any] = {"configured": raw is not None, "enabled": False, "time": None,
                                  "timezone": None, "next_run": None, "problem": None, "last": read_state(domain)}
        if raw is None:
            return result
        try:
            schedule = parse_schedule(raw)
        except ScheduleError as exc:
            result["problem"] = str(exc)
            return result
        known = self._due.get(domain_id)
        due = known[1] if known and known[0] == schedule else next_run(schedule, now)
        result.update(schedule.as_dict(), next_run=due.isoformat() if due else None)
        return result

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick(datetime.now(timezone.utc))
            except Exception:  # a broken domain must not stop the other schedules
                traceback.print_exc()
            await asyncio.sleep(self.interval)
