# common

Shared Python utilities copied from cursor projects (starting with `openfigi`). Intended to replace duplicated `lib/casted_dict.py` and `lib/db_connection.py` copies once each project is wired to this package.

**Status:** preparation only — sibling repos still use their local `lib/` copies; do not delete those until migration is explicit.

## Folder structure

```
cursor/common/          # git repo (this project)
  AGENTS.md             # cursor-wide agent contracts
  README.md
  pyproject.toml
  lib/                  # installable package (import: from lib.casted_dict import …)
    casted_dict.py
    db_connection.py
    __init__.py
  tests/
```

### Why `lib/` at the repo root (not `common/lib/` or `common/common/lib/`)

- The **repository** is already named `common`; nesting another `common/` package would be redundant.
- Existing cursor code imports `from lib.casted_dict import CastedDict` and `from lib.db_connection import DatabaseCredentials`. Keeping the top-level package name **`lib`** lets consumers switch to an editable path dependency without rewriting imports.
- Project-specific helpers (`conf_paths`, `_paths`, table prefixes, domain modules) stay in each repo; only cross-cutting utilities live here.

### Future layout (optional)

As more shared code moves in:

```
lib/
  casted_dict.py
  db_connection.py
  conf_paths.py      # generic resolve/load_conf — if deduplicated later
tests/
```

Domain packages (`openfigi`, `price_logger`, `mstack2`, …) remain in their own repos.

## Install (for development in this repo)

```bash
cd ~/cursor/common
uv sync --extra dev
uv run pytest
```

## Wire into another project (when ready)

In the consumer's `pyproject.toml`:

```toml
dependencies = ["cursor-common"]

[tool.uv.sources]
cursor-common = { path = "../common", editable = true }
```

Remove the consumer's duplicate `lib/casted_dict.py` and `lib/db_connection.py` only after imports and tests pass. Each project keeps its own `conf/` and path helper that passes an absolute credentials path into `DatabaseCredentials(...)`.
