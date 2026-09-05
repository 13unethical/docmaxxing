#!/usr/bin/env python3
"""Read-only hardware / ML-stack diagnostics for student training planning.

Does not download models, start training, or mutate datasets.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGES = [
    "torch",
    "transformers",
    "peft",
    "bitsandbytes",
    "trl",
    "unsloth",
    "accelerate",
    "datasets",
    "sentencepiece",
    "tokenizers",
    "safetensors",
    "flash_attn",
    "deepspeed",
    "vllm",
    "mlx",
    "mlx_lm",
]


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return None


def _sysctl(key: str) -> str | None:
    return _run(["sysctl", "-n", key])


def package_info(name: str) -> dict:
    try:
        mod = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "error": f"{type(exc).__name__}: {exc}"}
    info: dict = {
        "installed": True,
        "version": getattr(mod, "__version__", None),
    }
    if name == "torch":
        import torch

        info["cuda_available"] = bool(torch.cuda.is_available())
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        info["mps_available"] = bool(
            getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        )
        info["device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
        gpus = []
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpus.append(
                    {
                        "index": i,
                        "name": props.name,
                        "total_mem_gb": round(props.total_memory / (1024**3), 2),
                    }
                )
        info["gpus"] = gpus
    return info


def disk_info(path: Path) -> dict:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_gb": round(usage.total / (1024**3), 2),
        "used_gb": round(usage.used / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    mem_bytes = _sysctl("hw.memsize")
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version,
            "executable": sys.executable,
            "cpu_brand": _sysctl("machdep.cpu.brand_string"),
            "ncpu": _sysctl("hw.ncpu"),
            "physicalcpu": _sysctl("hw.physicalcpu"),
            "mem_bytes": int(mem_bytes) if mem_bytes and mem_bytes.isdigit() else mem_bytes,
            "mem_gb": round(int(mem_bytes) / (1024**3), 2)
            if mem_bytes and mem_bytes.isdigit()
            else None,
            "nvidia_smi": _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]),
            "system_profiler_chip": _run(
                [
                    "/usr/sbin/system_profiler",
                    "SPHardwareDataType",
                    "SPDisplaysDataType",
                ]
            ),
        },
        "disk": disk_info(repo),
        "packages": {name: package_info(name) for name in PACKAGES},
        "notes": [
            "Read-only diagnostic; no model download or training.",
            "Apple Silicon without CUDA cannot use bitsandbytes QLoRA / Unsloth CUDA path.",
        ],
    }
    out_dir = repo / "data" / "humanizer_training"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "student_env_diagnostics.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "mem_gb": report["host"]["mem_gb"], "disk_free_gb": report["disk"]["free_gb"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
