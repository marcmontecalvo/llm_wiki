#!/usr/bin/env python
"""Verify syntax of all promotion files."""

import py_compile
import sys
from pathlib import Path

files = [
    "src/llm_wiki/promotion/__init__.py",
    "src/llm_wiki/promotion/config.py",
    "src/llm_wiki/promotion/models.py",
    "src/llm_wiki/promotion/scorer.py",
    "src/llm_wiki/promotion/engine.py",
    "src/llm_wiki/daemon/jobs/promotion.py",
    "tests/unit/test_promotion_scorer.py",
    "tests/unit/test_promotion_engine.py",
    "tests/integration/test_promotion_workflow.py",
]

errors = []
for file in files:
    filepath = Path(file)
    if not filepath.exists():
        errors.append(f"File not found: {file}")
        continue

    try:
        py_compile.compile(str(filepath), doraise=True)
        print(f"✓ {file}")
    except py_compile.PyCompileError as e:
        errors.append(f"✗ {file}: {e}")
        print(f"✗ {file}")

if errors:
    print("\nErrors:")
    for error in errors:
        print(f"  {error}")
    sys.exit(1)
else:
    print("\n✅ All files have valid syntax!")
    sys.exit(0)
