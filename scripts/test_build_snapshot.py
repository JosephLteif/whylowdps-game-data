import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.build_snapshot import build_snapshot, parse_metadata_files


class BuildSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name) / "dist"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_metadata_rejects_unsafe_paths(self):
        with self.assertRaisesRegex(ValueError, "unsafe Raidbots path"):
            parse_metadata_files('{"files":["../secrets.json"]}')

    def test_parse_metadata_rejects_backslash_traversal_paths(self):
        for path in (r"..\secrets.json", r"dir\..\secrets.json"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "unsafe Raidbots path"):
                    parse_metadata_files(json.dumps({"files": [path]}))

    def test_parse_metadata_rejects_metadata_file(self):
        with self.assertRaisesRegex(ValueError, "metadata.json"):
            parse_metadata_files('{"files":["metadata.json"]}')

    def test_build_snapshot_writes_hashed_manifest_and_zip(self):
        payloads = {"metadata.json": b'{"files":["items.json"]}', "items.json": b"[]"}

        manifest = json.loads(
            build_snapshot(lambda path: payloads[path], self.output_dir).read_text()
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual({file["path"] for file in manifest["files"]}, set(payloads))
        self.assertTrue((self.output_dir / manifest["archive"]["name"]).is_file())

    def test_incomplete_fetch_writes_no_manifest(self):
        with self.assertRaises(OSError):
            build_snapshot(
                lambda path: b'{"files":["items.json"]}'
                if path == "metadata.json"
                else (_ for _ in ()).throw(OSError("down")),
                self.output_dir,
            )

        self.assertFalse((self.output_dir / "manifest.json").exists())

    @patch("scripts.build_snapshot.datetime")
    def test_archive_collision_preserves_existing_manifest(self, mock_datetime):
        mock_datetime.now.return_value = datetime(2026, 7, 9, tzinfo=timezone.utc)
        metadata = b'{"files":["items.json"]}'
        first_manifest = build_snapshot(
            lambda path: {"metadata.json": metadata, "items.json": b"first"}[path],
            self.output_dir,
        ).read_bytes()

        with self.assertRaises(FileExistsError):
            build_snapshot(
                lambda path: {"metadata.json": metadata, "items.json": b"second"}[path],
                self.output_dir,
            )

        self.assertEqual((self.output_dir / "manifest.json").read_bytes(), first_manifest)


if __name__ == "__main__":
    unittest.main()
