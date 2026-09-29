from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uc_bench.downloads import load_pinned_sources
from uc_bench.errors import ContractError


class DownloadContractTests(unittest.TestCase):
    def write_manifest(self, root: Path, path: str) -> None:
        config_root = root / "configs"
        config_root.mkdir()
        manifest = {
            "sources": [
                {
                    "id": "source",
                    "url": "https://example.org/data.gz",
                    "path": path,
                    "bytes": 10,
                    "sha256": "a" * 64,
                }
            ]
        }
        (config_root / "data_sources.json").write_text(json.dumps(manifest))

    def test_accepts_scoped_https_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, "data/raw/data.gz")
            source = load_pinned_sources(root)[0]
            self.assertEqual(source.relative_path, "data/raw/data.gz")

    def test_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, "../outside.gz")
            with self.assertRaisesRegex(ContractError, "escapes"):
                load_pinned_sources(root)


if __name__ == "__main__":
    unittest.main()
