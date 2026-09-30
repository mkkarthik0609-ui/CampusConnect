"""WSGI entrypoint for production servers (gunicorn on Render).

    gunicorn wsgi:app -c gunicorn.conf.py

`app.py` currently builds a module-level `app`; fall back to the factory if that ever changes.
"""
try:
    from app import app  # noqa: F401  (module-level app created by app.py)
except ImportError:
    from app import create_app

    app = create_app()

if __name__ == "__main__":
    app.run()
