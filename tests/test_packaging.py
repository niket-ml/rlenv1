from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uc_bench.packaging import StartStateBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StartStatePackagingTests(unittest.TestCase):
    def test_full_data_and_withheld_packages_are_distinct_and_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            builder = StartStateBuilder(PROJECT_ROOT)
            full = builder.build("full_data", output_root=output_root)
            withheld = builder.build("data_withheld", output_root=output_root)

            self.assertTrue((full.workspace_root / "data" / "metadata.csv").is_file())
            self.assertFalse((withheld.workspace_root / "data" / "metadata.csv").exists())
            self.assertTrue(
                (withheld.workspace_root / "data" / "DATA_WITHHELD.md").is_file()
            )
            self.assertNotEqual(full.package_digest, withheld.package_digest)
            for package in (full, withheld):
                manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
                self.assertTrue(manifest["sealed_sample_id_scan"]["passed"])
                self.assertFalse(any("gse92415_labels" in row["path"] for row in manifest["files"]))


if __name__ == "__main__":
    unittest.main()
