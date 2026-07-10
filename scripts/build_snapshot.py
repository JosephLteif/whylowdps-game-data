import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


RAIDBOTS_DATA_URL = "https://www.raidbots.com/static/data/live"
USER_AGENT = "WhyLowDps recovery snapshot (+https://github.com/WhyLowDps/whylowdps-game-data)"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_metadata_files(metadata_text: str) -> list[str]:
    raw_files = json.loads(metadata_text).get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("metadata files must be a non-empty list")

    paths = []
    for raw_path in raw_files:
        if not isinstance(raw_path, str):
            raise ValueError("metadata file path must be a string")
        path = PurePosixPath(raw_path)
        if (
            "\\" in raw_path
            or (len(raw_path) >= 2 and raw_path[1] == ":")
            or path.is_absolute()
            or ".." in path.parts
            or raw_path != path.as_posix()
        ):
            raise ValueError(f"unsafe Raidbots path: {raw_path}")
        if raw_path == "metadata.json":
            raise ValueError("metadata file list must not include metadata.json")
        paths.append(raw_path)

    if len(paths) != len(set(paths)):
        raise ValueError("metadata contains duplicate file paths")
    return paths


def build_snapshot(fetch: Callable[[str], bytes], output_dir: Path) -> Path:
    metadata = fetch("metadata.json")
    source_metadata_hash = sha256(metadata)
    paths = parse_metadata_files(metadata.decode("utf-8"))
    payloads = {"metadata.json": metadata}
    unavailable_paths = []
    for path in paths:
        try:
            payloads[path] = fetch(path)
        except HTTPError as error:
            if error.code != 404:
                raise
            unavailable_paths.append(path)
            print(f"Skipping unavailable Raidbots file listed by metadata: {path}")

    if unavailable_paths:
        metadata_payload = json.loads(metadata)
        metadata_payload["files"] = [path for path in paths if path not in unavailable_paths]
        payloads["metadata.json"] = (
            json.dumps(metadata_payload, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"snapshot-{timestamp}-{source_metadata_hash[:12]}.zip"

    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / archive_name
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, payload in payloads.items():
                archive.writestr(path, payload)

        archive_payload = archive_path.read_bytes()
        manifest = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_metadata_sha256": source_metadata_hash,
            "archive": {
                "name": archive_name,
                "sha256": sha256(archive_payload),
                "size": len(archive_payload),
            },
            "files": [
                {"path": path, "sha256": sha256(payload), "size": len(payload)}
                for path, payload in payloads.items()
            ],
        }
        manifest_path = temp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        archive_destination = output_dir / archive_name
        os.link(archive_path, archive_destination)
        archive_path.unlink()
        os.replace(manifest_path, output_dir / "manifest.json")

    return output_dir / "manifest.json"


def fetch_raidbots(path: str) -> bytes:
    request = Request(
        f"{RAIDBOTS_DATA_URL}/{quote(path, safe='/')}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a verified Raidbots recovery snapshot.")
    parser.add_argument("--output", type=Path, required=True, help="Directory for the archive and manifest")
    args = parser.parse_args()
    build_snapshot(fetch_raidbots, args.output)


if __name__ == "__main__":
    main()
