from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from uc_bench.errors import ContractError
from uc_bench.geo import normalize_metadata_key, read_geo_series_metadata
from uc_bench.hashing import sha256_file

SERIES_MATRIX = """!Series_title\t\"Example\"
!Series_geo_accession\t\"GSE1\"
!Sample_title\t\"before\"\t\"after\"
!Sample_geo_accession\t\"GSM1\"\t\"GSM2\"
!Sample_source_name_ch1\t\"biopsy\"\t\"biopsy\"
!Sample_platform_id\t\"GPL1\"\t\"GPL1\"
!Sample_characteristics_ch1\t\"patient: P1\"\t\"patient: P1\"
!Sample_characteristics_ch1\t\"time point: baseline\"\t\"time point: week 6\"
!series_matrix_table_begin
\"ID_REF\"\t\"GSM1\"\t\"GSM2\"
\"probe\"\t1.0\t2.0
!series_matrix_table_end
"""


class GeoMetadataTests(unittest.TestCase):
    def write_matrix(self, root: Path, content: str = SERIES_MATRIX) -> Path:
        path = root / "matrix.txt.gz"
        with gzip.open(path, mode="wt", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_reads_ordered_samples_and_characteristics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_matrix(Path(directory))
            series = read_geo_series_metadata(path)
            self.assertEqual(series.accession, "GSE1")
            self.assertEqual(series.platform_ids, ("GPL1",))
            self.assertEqual([sample.accession for sample in series.samples], ["GSM1", "GSM2"])
            self.assertEqual(series.samples[0].characteristic("time point"), "baseline")
            self.assertEqual(series.samples[1].characteristic("patient"), "P1")
            self.assertEqual(len(sha256_file(path)), 64)

    def test_rejects_misaligned_sample_metadata(self) -> None:
        malformed = SERIES_MATRIX.replace(
            '!Sample_title\t"before"\t"after"', '!Sample_title\t"before"'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_matrix(Path(directory), malformed)
            with self.assertRaisesRegex(ContractError, "Sample_title"):
                read_geo_series_metadata(path)

    def test_key_normalization_is_conservative(self) -> None:
        self.assertEqual(normalize_metadata_key("Week-6 Response"), "week_6_response")


if __name__ == "__main__":
    unittest.main()
