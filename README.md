# CI Triage Agent

Triage CI test failures automatically: detect flaky tests from their history, separate them from real regressions, and explain failures on every pull request.

> Status: early development (parsing JUnit XML test reports).

## Development setup (Windows PowerShell)

```powershell
py -m venv .venv                 # create a virtual environment (once; needs Python 3.12+)
.venv\Scripts\Activate.ps1       # activate it (every new terminal)
pip install -e ".[dev]"          # install the project + dev tools
```

macOS/Linux: `python3.12 -m venv .venv && source .venv/bin/activate`, then the same `pip install`.

## Common commands

```powershell
pytest -v               # run tests
ruff check .            # lint
ruff format .           # auto-format
```

CI runs lint, format check, and tests on every push to `main` and every pull request.
