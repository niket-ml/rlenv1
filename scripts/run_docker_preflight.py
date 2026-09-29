#!/usr/bin/env python3
"""Verify the local Docker agent image without contacting a model provider."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.docker_runtime import DockerWorkspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    runtime = DockerWorkspace(
        workspace_root=PROJECT_ROOT / "build" / "episodes" / "full_data",
        container_name="uc-bench-offline-preflight",
    )
    runtime.start()
    try:
        isolation = runtime.security_snapshot()
        command = runtime.run_command(
            "python -c \"import pandas as pd; "
            "frame=pd.read_csv('data/metadata.csv'); print(frame.shape)\""
        )
    finally:
        runtime.stop()
    output = {
        "isolation": isolation,
        "scientific_python_command": json.loads(command),
        "openrouter_contacted": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
