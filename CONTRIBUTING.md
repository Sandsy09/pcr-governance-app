# Contributing

## Ground rules

- `main` is never committed to directly. Every change gets its own branch and a pull request.
- Pull requests are **squash merged** — write commits along the way however you like, but leave
  the PR title as a proper [Conventional Commits](https://www.conventionalcommits.org/) subject,
  because that's what `git log` shows on `main` afterwards.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `chore:`, ...); a `commit-msg`
  hook enforces this on every commit, not just the squash commit.

## Development setup

```bash
uv sync --all-groups --locked
uv run pre-commit install
cp .env.example .env
uv run poe db:upgrade
```

`uv sync --all-groups --locked` installs the `dev`, `lint`, `test`, `typecheck` and `postgres`
dependency groups. `uv run pre-commit install` wires up both hook stages configured in
`.pre-commit-config.yaml` (`pre-commit` and `commit-msg`) — skipping it means lint/format issues
and malformed commit messages only surface in CI.

After an intentional dependency change, run `uv lock`, review the result, and commit the updated
`uv.lock`.

## Task reference

Tasks are defined once in `pyproject.toml` under `[tool.poe.tasks]` — don't duplicate them
elsewhere. Run any of them with `uv run poe <task>`.

| Command | Description |
| --- | --- |
| `uv run --locked poe check` | `lock:check` + `format:check` + `lint` + `typecheck` + `test` + `coverage` + `typecheck:pyright`, in order |
| `uv run poe lock:check` | Verify `uv.lock` matches declared dependencies |
| `uv run poe lint` / `poe lint:fix` | Ruff lint |
| `uv run poe format` / `poe format:check` | Ruff format |
| `uv run poe typecheck` | mypy (strict) |
| `uv run poe typecheck:pyright` | pyright |
| `uv run poe test` | pytest |
| `uv run poe coverage` | pytest with a coverage report |
| `uv run poe changelog` | regenerate `CHANGELOG.md` via git-cliff |
| `uv run poe serve` | `manage.py runserver`, loading `.env` |
| `uv run poe db:upgrade` | apply Alembic migrations to `PCR_DATABASE_URL` |
| `uv run poe db:revision -m "..."` | autogenerate a migration from model changes |
| `uv run poe db:check` | fail if models and migrations have drifted |
| `uv run poe pg:up` / `poe pg:down` | start/stop the local Postgres container (`compose.yaml`) |

`serve`, `db:upgrade`, `db:revision`, `db:check`, `pg:up` and `pg:down` load `.env` themselves
(poe's per-task `envfile`) — no need to export `PCR_DATABASE_URL` by hand for those. Every other
task above runs without touching `.env`.

Run a single test directly with pytest (not through poe):

```bash
uv run pytest tests/unit/test_approval_application_service.py::test_name
```

**Always run `uv run --locked poe check` before opening a pull request** — the outer `--locked`
stops `uv` from silently refreshing lock state ahead of the drift check.

## Architecture and where code goes

The app is layered/hexagonal: **domain → application → persistence**, with Django (`web`,
`config`) as a thin delivery layer. Dependencies point inward — the domain layer knows nothing
about Django or SQLAlchemy. See [CLAUDE.md](CLAUDE.md) for the full writeup; this section is the
short "where do I put this" version.

- **`domain/`** — pure business logic, no I/O. All models (`pcr.py`, `approval.py`, `audit.py`)
  are frozen Pydantic models: "updating" state means building a new object with
  `model_copy(update={...})`, never mutating in place.
  - `transitions.py` (`PCRStateMachine`) enforces the PCR status graph
    (`ALLOWED_TRANSITIONS`) — **add new legal transitions there**, not as ad hoc checks
    elsewhere.
  - `approval_engine.py` (`ApprovalEngine`) is a stateless collection of `staticmethod`/
    `classmethod`s driving approval workflows. It operates purely on domain objects — no
    persistence dependency.
  - `errors.py` defines the `PCRDomainError` hierarchy raised by domain rule violations.
- **`application/`** — use-case orchestration. Each service (`PCRApplicationService`,
  `ApprovalApplicationService`, `PCRQueryService`, `PCRRevisionService`) takes a
  `UnitOfWorkFactory` and wraps each use case in a single
  `with self._uow_factory() as uow: ... uow.commit()` block, composing domain calls with
  repository reads/writes and `AuditEvent` recording. `UnitOfWork` is a `Protocol` — application
  code depends only on it, never on SQLAlchemy. `application/errors.py` defines the
  application-facing exceptions (`PCRNotFoundError`, `PCRCodeAlreadyExistsError`, ...) that the
  web layer catches.
- **`persistence/`** — the only SQLAlchemy-aware layer. `models.py` holds the ORM entities, a
  *separate* schema from the domain Pydantic models. `mappers.py` converts explicitly between
  domain objects and ORM records in both directions — there is no ORM-to-domain magic, so a new
  field needs updating in the domain model, the ORM model, and both mapper functions.
  `repositories.py` defines repository `Protocol`s; `sqlalchemy_*_repository.py` implement them.
  Domain datetimes are always timezone-aware; `mappers.to_database_datetime`/
  `from_database_datetime` convert to/from the naive UTC values stored in the database.
- **`web/`** — Django views (`views.py`), forms, presenters (view-model formatting), and
  templates. Views are intentionally thin: call `web/services.get_services()`, wrap
  configuration-dependent views with the `configuration_required` decorator, and translate
  application errors into HTTP responses/messages.

Common changes and where they go:

- **Adding a field to a PCR/approval/audit model:** domain model → ORM model
  (`persistence/models.py`) → both mapper functions (`persistence/mappers.py`) → a migration
  (`uv run poe db:revision -m "..."`) → form/presenter/template if it's user-facing.
- **Adding a new PCR status transition:** edit `ALLOWED_TRANSITIONS` in
  `domain/transitions.py`. Don't add transition checks anywhere else.
- **Adding a new use case:** add a method to the relevant application service, wrapped in one
  `with self._uow_factory() as uow: ...` block, composing domain calls with repository
  read/writes, and record an `AuditEvent` for anything that changes state.
- **Adding a view:** keep it thin — call `get_services()`, decorate with
  `@configuration_required` if it touches PCR data, and catch `PCRApplicationError` subclasses
  to turn them into form errors or messages rather than letting them propagate.
- **Adding a persistence backend:** repository and unit-of-work abstractions are
  `typing.Protocol`s, not ABCs — a new backend just needs to satisfy the shape, no base class to
  extend.

## Database migrations

Schema changes go through Alembic, not manual DDL:

```bash
uv run poe db:revision -m "add foo column to pcr"
```

Review the autogenerated migration under `persistence/migrations/versions/` before committing it
— autogeneration doesn't always get everything right — and run `uv run poe db:check` to confirm
models and migrations agree. CI's `migrations` job re-runs both `db:upgrade` and `db:check`
against a fresh SQLite database and a fresh Postgres database, so drift that only shows up on one
backend still gets caught.

## Testing

```text
tests/
  conftest.py     Configures DJANGO_SETTINGS_MODULE and calls django.setup() before tests run.
  fakes.py         In-memory fakes for the repository/unit-of-work protocols, used by unit tests
                   instead of a real database.
  unit/            Domain and application-layer tests, driven through the fakes above.
  integration/     Tests that exercise the real SQLAlchemy/Alembic stack against a database.
  fixtures/        Shared pytest fixtures.
```

`tests/**` is exempted from the `D`, `ANN` and `S101` (assert) lint rules — don't add docstrings
or type annotations to test code just to satisfy ruff, and use plain `assert`.

Run the whole suite with `uv run poe test`, or a single test directly with pytest (see the task
reference above). `uv run poe coverage` adds a coverage report; the underlying fail-under
threshold lives in `.coveragerc`.

When adding a use case, prefer a unit test against the application service using the fakes in
`tests/fakes.py` over standing up a real database — reserve `tests/integration` for exercising
mapper/repository/migration behavior that the fakes can't represent.

## Code style and typing

- Ruff enables `E`, `W`, `F`, `I`, `N`, `UP`, `B`, `A`, `C4`, `SIM`, `PTH`, `RUF` and `ANN`
  (flake8-annotations) — new code needs type annotations. Line length is 100.
  `uv run poe lint:fix` and `uv run poe format` apply what can be auto-fixed.
- mypy runs in `strict` mode with `warn_unreachable` and `warn_unused_ignores`; pyright runs
  separately as a second opinion (`uv run poe typecheck:pyright`). Both are part of `poe check`.

## Branching, commits and PRs

Branch names are `<type>/<short-slug>`, kebab-case, where `<type>` is a Conventional Commits type
(`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`) — pick the type the branch's
eventual squash commit will carry, e.g. `fix/retry-timeout` or `docs/update-readme`. The commit
history in this repo also uses scopes for larger areas, e.g. `feat(web): ...`,
`feat(persistence): ...`, `feat(application): ...` — use one where it adds clarity.

```bash
git switch -c <type>/<short-slug>
# ... commit(s) ...
git push -u origin <type>/<short-slug>
```

Open a pull request and wait for CI to pass, then **squash merge**, editing the squash commit
subject into a proper Conventional Commits subject rather than leaving the default title. Fill in
the PR template's checklist (`.github/pull_request_template.md`): `poe check` passes locally,
tests are added/updated for behavior changes, and docs are updated if user-facing behavior
changed.

Pull requests are routed for review to `@Sandsy09/pcr-governance-app-maintainers` through
[`.github/CODEOWNERS`](.github/CODEOWNERS).

## Continuous integration

Every push to `main` and every pull request runs `.github/workflows/ci.yml`:

| Job | What it checks |
| --- | --- |
| `lint` | `lock:check`, `format:check`, `lint` |
| `typecheck` | mypy strict |
| `type-check-pyright` | pyright |
| `test` | pytest on Python 3.11, 3.12 and 3.13, plus a coverage report (uploaded as an artifact from the 3.13 run) |
| `migrations` | `alembic upgrade head` then `alembic check` against both a fresh SQLite file and a Postgres service container |
| `build` | builds the sdist/wheel and checks metadata with `twine check` |

Remote GitHub Actions under `.github/workflows/` are pinned to full commit SHAs with the release
tag in a same-line comment — keep that form when updating them; Dependabot updates both the SHA
and the comment together weekly.

## Dependencies

After changing dependency declarations, run `uv lock` deliberately, then review and commit the
resulting `uv.lock`. Dependabot opens weekly PRs for both `uv` dependencies (grouped by
dev-tooling for minor/patch bumps) and GitHub Actions.

## Changelog and releases

`CHANGELOG.md` is generated from Conventional Commits history by
[git-cliff](https://github.com/orhun/git-cliff) (`uv run poe changelog`), configured in
`cliff.toml`. `chore`/`build`/`ci` commits are skipped from the changelog by design. The package
version lives in `pyproject.toml`.

## Security

See [SECURITY.md](SECURITY.md) for reporting a vulnerability and the app's current security
posture. There is no real authentication in the app yet — the "current actor" is a free-text
string used only to attribute PCR actions (`web/context_processors.py`,
`web/services.get_default_actor`). Don't build real authorization logic on top of it without
discussing the change first.

## Repository

Clone with `git clone https://github.com/Sandsy09/pcr-governance-app.git`.
