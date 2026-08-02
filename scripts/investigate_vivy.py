#!/usr/bin/env python3
"""
investigate_vivy.py

Utility script to perform Phase 1 investigation of the Vivy AI codebase.
It runs **without modifying any existing project files** and generates
artifacts in the `scratch/` directory for later review.

The script performs the following steps:
1. **Project structure inventory** – recursively walks the repository and
   writes `scratch/project_structure.json`.
2. **Import graph generation** – parses every ``.py`` file, extracts
   ``import`` and ``from … import`` statements, builds a directed graph of
   internal module dependencies and writes:
   * ``scratch/import_graph.json`` – machine‑readable mapping.
   * ``scratch/import_graph.mmd`` – Mermaid diagram for visualisation.
3. **Threading / async usage detection** – finds usages of ``threading``,
   ``multiprocessing``, ``concurrent.futures`` and ``asyncio`` and records
   the originating file and line number in ``scratch/thread_usage.json``.
4. **GPU/CPU device hints** – searches for common device selection patterns
   (e.g., ``torch.device``, ``cuda`` strings) and writes
   ``scratch/device_hints.json``.
5. **Hard‑coded literal scan** – simple regex search for paths, IDs,
   thresholds, model names etc. (configurable in ``LITERAL_PATTERNS``) and
   exports ``scratch/hardcoded_literals.json``.
6. **Summary markdown report** – consolidates the above findings into a
   human‑readable ``scratch/investigation_report.md`` with embedded Mermaid
   diagrams.

All output files are placed under ``scratch/`` so the original source tree
remains untouched, satisfying the "no code rewrite" rule.
"""

import os
import json
import ast
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]  # d:\Vivy
SCRATCH_DIR = ROOT_DIR / "scratch"
SCRATCH_DIR.mkdir(exist_ok=True)

def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def write_text(path: Path, text: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

# 1. Project structure inventory
structure = {}
for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
    rel = os.path.relpath(dirpath, ROOT_DIR)
    structure[rel] = filenames
write_json(SCRATCH_DIR / "project_structure.json", structure)

# 2. Import graph generation
import_graph = {}
for py_path in ROOT_DIR.rglob("*.py"):
    module = py_path.relative_to(ROOT_DIR).with_suffix("").as_posix().replace("/", ".")
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        continue
    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                deps.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                deps.add(node.module.split(".")[0])
    import_graph[module] = sorted(deps)
write_json(SCRATCH_DIR / "import_graph.json", import_graph)
# Mermaid diagram
mermaid_nodes = []
mermaid_edges = []
for mod, deps in import_graph.items():
    mermaid_nodes.append(f"    {mod.replace('.', '_')}[\"{mod}\"]")
    for dep in deps:
        mermaid_edges.append(f"    {mod.replace('.', '_')} --> {dep.replace('.', '_')}")
mermaid_content = "graph TD\n" + "\n".join(mermaid_nodes + mermaid_edges) + "\n"
write_text(SCRATCH_DIR / "import_graph.mmd", mermaid_content)

# 3. Threading / async usage detection
thread_usage = []
THREAD_LIBS = {"threading", "multiprocessing", "concurrent.futures", "asyncio"}
for py_path in ROOT_DIR.rglob("*.py"):
    for lineno, line in enumerate(py_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        stripped = line.strip()
        for lib in THREAD_LIBS:
            if lib in stripped:
                thread_usage.append({
                    "file": str(py_path.relative_to(ROOT_DIR)),
                    "line": lineno,
                    "code": stripped,
                    "library": lib,
                })
write_json(SCRATCH_DIR / "thread_usage.json", thread_usage)

# 4. GPU/CPU device hints
DEVICE_PATTERNS = [r"torch\.device\(['\"]cuda['\"]\)", r"cuda:\d+", r"device=\s*['\"]cpu['\"]"]
device_hints = []
for py_path in ROOT_DIR.rglob("*.py"):
    content = py_path.read_text(encoding="utf-8", errors="ignore")
    for pat in DEVICE_PATTERNS:
        for match in re.finditer(pat, content):
            device_hints.append({
                "file": str(py_path.relative_to(ROOT_DIR)),
                "match": match.group(0),
            })
write_json(SCRATCH_DIR / "device_hints.json", device_hints)

# 5. Hard‑coded literal scan (paths, IDs, thresholds, model names)
LITERAL_PATTERNS = [r"[A-Za-z0-9_/\\.-]+\.pth", r"[A-Za-z0-9_/\\.-]+\.onnx", r"\b\d{3,}\b", r"(threshold|THRESHOLD)\s*=\s*\d+\.\d+"]
literals = []
for py_path in ROOT_DIR.rglob("*.py"):
    content = py_path.read_text(encoding="utf-8", errors="ignore")
    for pat in LITERAL_PATTERNS:
        for match in re.finditer(pat, content):
            literals.append({
                "file": str(py_path.relative_to(ROOT_DIR)),
                "pattern": pat,
                "value": match.group(0),
            })
write_json(SCRATCH_DIR / "hardcoded_literals.json", literals)

# 6. Summary markdown report
report_lines = ["# Vivy AI Phase 1 Investigation Report",
"\n## Project Structure", f"- Total files: {len(list(ROOT_DIR.rglob('*.py')))}",
"\n## Import Dependency Graph", "```mermaid", mermaid_content, "```",
"\n## Threading / Async Usage", f"Found {len(thread_usage)} occurrences.", "```json", json.dumps(thread_usage, indent=2), "```",
"\n## Device Selection Hints", f"Found {len(device_hints)} hints.", "```json", json.dumps(device_hints, indent=2), "```",
"\n## Potential Hard‑coded Literals", f"Found {len(literals)} matches.", "```json", json.dumps(literals, indent=2), "```",
]
write_text(SCRATCH_DIR / "investigation_report.md", "\n".join(report_lines))

print("Investigation artifacts generated in", SCRATCH_DIR)
