from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uc_bench.errors import ContractError
from uc_bench.hashing import canonical_sha256, hash_artifacts, verify_artifact_hashes


class CanonicalHashingTests(unittest.TestCase):
    def test_mapping_key_order_does_not_change_digest(self) -> None:
        self.assertEqual(canonical_sha256({"a": 1, "b": 2}), canonical_sha256({"b": 2, "a": 1}))

    def test_artifact_path_order_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")
            hashes = hash_artifacts(root, ("b.txt", "a.txt"))
            self.assertEqual(tuple(hashes), ("b.txt", "a.txt"))

    def test_workspace_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ContractError):
            hash_artifacts(Path(directory), ("../outside.txt",))

    def test_mutation_details_name_changed_artifact(self) -> None:
        with self.assertRaisesRegex(ContractError, r"changed=\['model.bin'\]"):
            verify_artifact_hashes({"model.bin": "before"}, {"model.bin": "after"})


if __name__ == "__main__":
    unittest.main()
