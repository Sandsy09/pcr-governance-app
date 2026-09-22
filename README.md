# PCR Governance App

Internal Python application for PCR management

## Requirements

- Python 3.11+ (developed against 3.13)
- [uv](https://docs.astral.sh/uv/)

## Development

```bash
uv sync --all-groups --locked
```

Run `uv lock` deliberately after changing dependency declarations, then
review and commit the resulting `uv.lock` update.

### Tasks

Tasks are defined once in `pyproject.toml` under `[tool.poe.tasks]`.

| Command | Description |
| --- | --- |
| `uv run --locked poe check` | Lock drift and everything below, in order |
| `uv run poe lock:check` | Verify `uv.lock` matches declared dependencies |
| `uv run poe lint` | Ruff lint |
| `uv run poe format` | Ruff format |
| `uv run poe typecheck` | mypy |
| `uv run poe test` | pytest |

Run `uv run --locked poe check` before pushing. The outer `--locked` prevents
uv from silently refreshing lock state before the drift check runs.

## Project structure

```text
src/pcr_governance_app/   Package source
tests/                            Test suite
```
## Environment variables

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

`.env` is git-ignored. `.env.example` is tracked -- keep every entry in it a
placeholder, never a real value.

## Repository

<https://github.com/Sandsy09/pcr-governance-app>

Clone with
`git clone https://github.com/Sandsy09/pcr-governance-app.git`,
or install this package directly from GitHub:

```bash
uv add git+https://github.com/Sandsy09/pcr-governance-app
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see
[SECURITY.md](SECURITY.md) -- do not open a public issue.

## License

See [LICENSE](LICENSE).
