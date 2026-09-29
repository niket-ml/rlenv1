#!/usr/bin/env python3
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc16_analysis import analyze_rc16_sentinel, write_rc16_report

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    value = analyze_rc16_sentinel(root)
    report = write_rc16_report(root, value)
    print(json.dumps({"conclusion": value["conclusion"], "report": report.as_posix()}, indent=2))
