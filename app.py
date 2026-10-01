"""Tiny local runner:  venv\\Scripts\\python.exe app.py

Equivalent to ``python -m uvicorn api.main:app --port 5000``. Set DEBUG=1 for
auto-reload and the /docs pages; HOST / PORT override the bind address. In production use the
uvicorn command from docs/api/ARCHITECTURE.md (one process) instead.
"""
import os

import uvicorn


def _flag(*names):
    return any(os.environ.get(n, "").strip().lower() in ("1", "true", "yes", "on") for n in names)


if __name__ == "__main__":
    production = (os.environ.get("APP_ENV") or "").strip().lower() == "production"
    debug = _flag("DEBUG") and not production
    uvicorn.run(
        "api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        reload=debug,
        # The app reads X-Forwarded-* itself (TRUST_PROXY); uvicorn must not also rewrite the client.
        proxy_headers=False,
    )
