"""Persistent, user-editable bot settings stored as JSON on the data volume."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Settings:
    path: Path = field(repr=False)
    timezone: str = "Asia/Tashkent"
    report_time: str = "23:59"  # HH:MM in `timezone`, on the last day of each month
    report_enabled: bool = True
    last_report_month: str | None = None  # "YYYY-MM" of the last month sent automatically

    @classmethod
    def load(cls, path: Path, default_timezone: str) -> "Settings":
        settings = cls(path=path, timezone=default_timezone)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for key, value in data.items():
                if hasattr(settings, key) and key != "path":
                    setattr(settings, key, value)
        return settings

    def save(self) -> None:
        data = asdict(self)
        data.pop("path")
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def report_hour_minute(self) -> tuple[int, int]:
        hour, minute = self.report_time.split(":")
        return int(hour), int(minute)
