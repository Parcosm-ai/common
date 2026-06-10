# common

Shared Policies and library code 

**Status:** under development

## Folder structure

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
