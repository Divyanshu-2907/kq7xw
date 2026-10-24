"""Vercel Python entrypoint.

Vercel's Python runtime serves any ASGI application exported as `app` from a
file under `api/`. The application itself lives in `backend/app`, which is kept
outside this directory so the same code runs under Docker, under `uvicorn`
locally, and in the test suite without a second copy.

`backend/` is placed on `sys.path` rather than imported as `backend.app.main`,
so the package resolves identically here and in the container, where
`backend/app` is copied to `/srv/app`.

`vercel.json` pulls `backend/**` into the function bundle, which is what makes
the committed CSV.gz snapshot available at request time: `app.data` resolves it
relative to its own file, so the directory layout has to survive the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402  (path must be set before this import)

__all__ = ["app"]
