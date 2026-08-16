"""Validate the cross-file invariants required before publishing recovery data."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


REQUIRED_FILES = {"seasons.json", "instances.json", "talents.json", "class-traits.json", "bonuses.json"}


def _json_payloads(snapshot_dir: Path, archive_name: str | None = None) -> dict[str, Any]:
    if archive_name:
        archive_path = snapshot_dir / archive_name
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            return {
                name: json.loads(archive.read(name).decode("utf-8"))
                for name in names
                if name.endswith(".json")
            }
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in snapshot_dir.glob("*.json")
        if path.name != "manifest.json"
    }


def _array(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return [item for item in value[key] if isinstance(item, dict)]
    return []


def validate_payloads(payloads: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FILES - payloads.keys())
    if missing:
        raise ValueError(f"snapshot is missing required files: {', '.join(missing)}")

    seasons = _array(payloads["seasons.json"], "seasons")
    active = [season for season in seasons if season.get("active") is True]
    if len(active) != 1:
        raise ValueError(f"snapshot must contain exactly one active season (found {len(active)})")
    short_name = str(active[0].get("shortName") or active[0].get("short_name") or "").strip().lower()
    if not short_name:
        raise ValueError("active season has no short name")

    instances = _array(payloads["instances.json"], "instances")
    if not any(instance.get("id") == -1 for instance in instances):
        raise ValueError("snapshot is missing the Mythic+ pool")
    seasonal_pools = [
        instance
        for instance in instances
        if isinstance(instance.get("id"), int)
        and instance["id"] < 0
        and short_name
        in f"{instance.get('type') or ''} {instance.get('name') or ''}".lower()
    ]
    if not seasonal_pools:
        raise ValueError(f"snapshot has no current-season pool for {short_name}")

    for required in ("talents.json", "class-traits.json", "bonuses.json"):
        value = payloads[required]
        if not value:
            raise ValueError(f"snapshot file is empty: {required}")

    conversion_id = active[0].get("itemConversionId")
    if conversion_id is not None and "item-conversions.json" not in payloads:
        raise ValueError("active season has no item-conversions.json payload")
    if conversion_id is not None and "item-conversions.json" in payloads:
        conversions = payloads["item-conversions.json"]
        if not isinstance(conversions, dict) or str(conversion_id) not in conversions:
            raise ValueError(f"active season conversion group is missing: {conversion_id}")
        group = conversions[str(conversion_id)]
        if not isinstance(group, dict) or not group.get("bonusIds"):
            raise ValueError(f"active season conversion group has no bonus IDs: {conversion_id}")


def validate_snapshot(snapshot_dir: Path) -> None:
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    archive_name = manifest.get("archive", {}).get("name")
    payloads = _json_payloads(snapshot_dir, archive_name)
    validate_payloads(payloads)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Raidbots recovery snapshot")
    parser.add_argument("snapshot_dir", type=Path)
    args = parser.parse_args()
    validate_snapshot(args.snapshot_dir)
    print("snapshot validation passed")


if __name__ == "__main__":
    main()
