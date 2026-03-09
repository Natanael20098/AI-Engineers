"""
Root conftest.py – configures the Python path for the full test suite.

Adds the repository root and the services/ subdirectory to sys.path so that
both sets of tests can resolve their imports without relative-import gymnastics:

  - tests/integration/aws/   → imports from infra.aws.*
  - tests/aws/               → imports from infra.aws.*
  - services/tests/          → imports from authentication.*, loan_management.*
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(__file__)
_SERVICES_ROOT = os.path.join(_REPO_ROOT, "services")

for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)
