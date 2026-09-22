# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency management and tasks go through `uv`; task definitions live once in
`pyproject.toml` under `[tool.poe.tasks]` — don't duplicate them elsewhere.

```bash
uv sync --all-groups --locked        # install (dev, lint, test, typecheck groups)
uv run --locked poe check            # lock:check + format:check + lint + typecheck + test + coverage + pyright, in order
```

Individual tasks:

| Command | Description |
| --- | --- |
| `uv run poe lock:check` | Verify `uv.lock` matches declared dependencies |
| `uv run poe lint` / `poe lint:fix` | Ruff lint |
| `uv run poe format` / `poe format:check` | Ruff format |
| `uv run poe typecheck` | mypy (strict) |
| `uv run poe typecheck:pyright` | pyright |
| `uv run poe test` | pytest |
| `uv run poe coverage` | pytest with coverage report |
| `uv run poe changelog` | regenerate `CHANGELOG.md` via git-cliff |

Run a single test directly with pytest (not through poe):

```bash
uv run pytest tests/test_smoke.py::test_version_is_available
```

After changing dependency declarations, run `uv lock` deliberately, then review and commit the
resulting `uv.lock`.

Always run `uv run --locked poe check` before pushing — the outer `--locked` stops `uv` from
silently refreshing lock state ahead of the drift check.

### Running the app

The web app is Django. `DJANGO_SETTINGS_MODULE` defaults to
`pcr_governance_app.config.settings` via `manage.py`. The app-data database connection is
separate from Django's own database (see Architecture) and is required at runtime:

```bash
cp .env.example .env   # then fill in real values; .env is git-ignored
uv run python manage.py runserver
```

`PCR_DATABASE_URL` must be set or any view touching PCR data renders a 503 configuration-error
page (`AppConfigurationError`, caught by the `configuration_required` view decorator).

## Architecture

This is a small layered/hexagonal application: **domain → application → persistence**, with
Django (`web`, `config`) as a thin delivery layer on top. Dependencies point inward; the domain
layer knows nothing about Django or SQLAlchemy.

- **`domain/`** — pure business logic, no I/O. All models (`pcr.py`, `approval.py`, `audit.py`)
  are frozen Pydantic models; state changes always return a new instance via `model_copy`, never
  mutate in place.
  - `transitions.py` (`PCRStateMachine`) enforces the PCR status graph (`ALLOWED_TRANSITIONS`) —
    add new legal transitions there, not ad hoc checks elsewhere.
  - `approval_engine.py` (`ApprovalEngine`) is a stateless collection of `staticmethod`/
    `classmethod`s that drive approval workflows (stage/requirement satisfaction, approve/
    request-changes/reject/cancel). It operates purely on domain objects passed in — it has no
    dependency on persistence.
  - `errors.py` defines the `PCRDomainError` hierarchy raised by domain rule violations.

- **`application/`** — use-case orchestration. Each service (`PCRApplicationService`,
  `ApprovalApplicationService`, `PCRQueryService`, `PCRRevisionService`) takes a
  `UnitOfWorkFactory` and wraps each use case in a single `with self._uow_factory() as uow: ...
  uow.commit()` block, composing domain calls (state machine / approval engine) with repository
  reads/writes and `AuditEvent` recording. `UnitOfWork` (`application/unit_of_work.py`) is a
  `Protocol` exposing `pcrs`, `audits`, `approval_routes`, `approval_workflows` repositories plus
  `commit`/`rollback` — application code depends only on this protocol, never on SQLAlchemy.
  `application/errors.py` defines the application-facing exceptions (e.g. `PCRNotFoundError`,
  `PCRCodeAlreadyExistsError`) that the web layer catches.

- **`persistence/`** — the only SQLAlchemy-aware layer. `models.py` holds the ORM entities
  (`PCRRecord`, `ApprovalWorkflowRecord`, etc.), which are a *separate* schema from the domain
  Pydantic models. `mappers.py` converts explicitly between domain objects and ORM records in
  both directions (`pcr_to_record` / `pcr_record_to_domain`, etc.) — there is no ORM-to-domain
  magic, so new fields need updating in the domain model, the ORM model, and both mapper
  functions. `repositories.py` defines the repository `Protocol`s that `application/` depends on;
  `sqlalchemy_*_repository.py` implement them. `SqlAlchemyUnitOfWork`
  (`persistence/unit_of_work.py`) implements the `UnitOfWork` protocol, opening a `Session` per
  `with` block and rolling back on exception or missing commit. Domain datetimes are always
  timezone-aware; `mappers.to_database_datetime`/`from_database_datetime` convert to/from the
  naive UTC values stored in SQLite.

- **`web/`** — Django views (`views.py`), forms, presenters (view-model formatting, e.g. status
  labels), and templates. Views are intentionally thin: they call into
  `web/services.get_services()` (an `lru_cache`d `AppServices` built from `PCR_DATABASE_URL`,
  holding the application services and a shared SQLAlchemy engine) and translate application
  errors into HTTP responses/messages. There is no real authentication: the "current actor" is a
  free-text string stored in the Django session via the `development-actor` view
  (`set_actor`/`current_actor`), used only for attributing PCR actions — do not build real
  authorization logic on top of it without discussing the change first.

- **Two separate databases**: Django's own `DATABASES["default"]` (SQLite, for Django's built-in
  session app — sessions actually use `signed_cookies`, so this is effectively unused for app
  data) is distinct from the SQLAlchemy engine/session created from `PCR_DATABASE_URL` in
  `web/services.py`, which is where all PCR/approval/audit data lives. Don't assume Django's ORM
  or `manage.py migrate` touches PCR data — there are no Alembic migrations checked in yet even
  though `alembic` is a declared dependency.

- **`rendering/`** currently contains only an empty `templates/` placeholder — not yet wired up.

### Conventions worth knowing

- Domain and application models are frozen/immutable; "updating" state means building a new
  object with `model_copy(update={...})`, not assigning attributes.
- Repository and unit-of-work abstractions are `typing.Protocol`s, not ABCs — new persistence
  backends just need to satisfy the shape.
- Ruff config enables `ANN` (flake8-annotations) and ruff/mypy are both run in strict-ish modes;
  `tests/**` is exempted from `D`, `ANN`, and `S101` (assert) lint rules.
- Commits follow Conventional Commits (enforced by a `commit-msg` pre-commit hook); branches are
  `<type>/<short-slug>`; `main` is never committed to directly — every change is a PR, squash-merged.
