#!/usr/bin/env bash
# Prepare a rented CUDA GPU host for student training: venv + deps + sanity check.
# Usage (from the repo root on the GPU host): bash scripts/setup_student_gpu_host.sh
set -euo pipefail

cd "$(dirname "$0")/.."
python3 -m venv .venv-student
.venv-student/bin/pip install -q --upgrade pip
.venv-student/bin/pip install -q -r requirements-student.txt
.venv-student/bin/python - <<'PY'
import torch, transformers, peft, trl
assert torch.cuda.is_available(), "CUDA GPU not visible"
props = torch.cuda.get_device_properties(0)
print(f"GPU {props.name} {props.total_memory / 2**30:.0f} GiB, bf16={torch.cuda.is_bf16_supported()}")
print(f"torch {torch.__version__} transformers {transformers.__version__} peft {peft.__version__} trl {trl.__version__}")
PY
