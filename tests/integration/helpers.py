from __future__ import annotations

import datetime
from typing import Any


def update_raw_records(raw_authors: list[dict[str, Any]], raw_rules: list[dict[str, Any]]) -> None:
    for raw_author in raw_authors:
        raw_author["dob"] = datetime.datetime.strptime(raw_author["dob"], "%Y-%m-%d").date()
        raw_author["created_at"] = datetime.datetime.strptime(raw_author["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc,
        )
        raw_author["updated_at"] = datetime.datetime.strptime(raw_author["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc,
        )
    for raw_rule in raw_rules:
        raw_rule["created_at"] = datetime.datetime.strptime(raw_rule["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc
        )
        raw_rule["updated_at"] = datetime.datetime.strptime(raw_rule["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc
        )
