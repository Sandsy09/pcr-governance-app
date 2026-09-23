# PCR Governance App

Internal Django application for managing **Policy Change Requests (PCRs)** — the record of a
proposed change to company policy, its rationale, its revision history, and (as the approval
workflow feature lands) who signed off on it and when.

## Features / current status

Today, through the web UI:

- **PCR Register** (`/`) — list every PCR, with free-text search (PCR code, policy code, title)
  and a status filter.
- **Create PCR** (`/pcrs/new/`) — raise a new PCR: title, description, change type, rationale,
  current vs. proposed policy, affected sections, impact summary, optional technical-change
  details, communication targets, and an optional "supersedes" link to an existing PCR.
- **PCR detail** (`/pcrs/<id>/`) — the current revision, full revision history, the audit trail,
  and the active approval workflow (once one exists).
- **Current user** (header) — a free-text "current user" selector used to attribute actions.
  There is no real authentication behind it — see [SECURITY.md](SECURITY.md).

Implemented in the application layer but **not yet wired up to the UI**: submitting a PCR for
review, resubmitting after changes are required, withdrawing a PCR, and approving / requesting
changes / rejecting through an approval workflow
(`src/pcr_governance_app/application/pcr_service.py`,
`src/pcr_governance_app/application/approval_service.py`). There's also no UI or seed data yet
for defining approval routes.

## Quick start

Requirements:

- Python 3.11+ (developed against 3.13)
- [uv](https://docs.astral.sh/uv/)
- Docker, only if you want to run Postgres locally instead of SQLite (see below)

```bash
git clone https://github.com/Sandsy09/pcr-governance-app.git
cd pcr-governance-app
uv sync --all-groups --locked
cp .env.example .env      # defaults to a local SQLite database — see "Database backends"
uv run poe db:upgrade      # apply migrations to create the PCR schema
uv run poe serve
```

Then open <http://127.0.0.1:8000/>.

## Using the app

1. **Set a current user.** Type a name or email into "Current user" in the header and click
   "Set" — actions you take (creating a PCR, and eventually approvals) are attributed to this
   value. It's stored in your session, not in the database.
2. **Create a PCR.** Go to "Create PCR", fill in the required fields, and submit. If
   "Technical change required" is checked, technical change details become required too.
3. **Browse the register.** Search by PCR code, policy code or title, and narrow by status with
   the filter checkboxes.
4. **Review a PCR.** Open a row from the register to see its current revision, prior revisions,
   audit trail, and (once submitted) its approval workflow progress.

## PCR lifecycle

A PCR's `status` moves through a fixed state graph enforced by
`src/pcr_governance_app/domain/transitions.py` (`PCRStateMachine.ALLOWED_TRANSITIONS`) — treat
that file as the source of truth, not this table:

| From | Can move to |
| --- | --- |
| `draft` | `in_review`, `withdrawn` |
| `in_review` | `changes_required`, `rejected`, `approved`, `withdrawn` |
| `changes_required` | `draft`, `withdrawn` |
| `approved` | `effective` |
| `effective` | `superseded` |
| `rejected`, `superseded`, `withdrawn` | *(terminal — no further transitions)* |

Every edit to a PCR's content creates a new immutable **revision** rather than mutating the
current one, and every state-changing action is recorded as an **audit event** — both visible on
the PCR detail page.

## Configuration

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

`.env` is git-ignored. `.env.example` is tracked — keep every entry in it a placeholder, never a
real value.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `PCR_DATABASE_URL` | Yes | *(none)* | SQLAlchemy URL for the PCR/approval/audit data. Any view touching PCR data renders a 503 configuration-error page if this is unset. |
| `PCR_POSTGRES_USER` / `PCR_POSTGRES_PASSWORD` / `PCR_POSTGRES_DB` | Only for the Postgres option | *(none)* | Read by `compose.yaml` to create the local Postgres container. |
| `PCR_DEFAULT_ACTOR` | No | *(empty)* | Fallback "current user" shown before anyone sets one in the session. |
| `PCR_DEBUG` | No | `true` | Django `DEBUG`. Set to `false` outside local development. |
| `PCR_DJANGO_SECRET_KEY` | No | an insecure built-in value | Django `SECRET_KEY`, which signs session/message cookies. Set a real value outside local development. |
| `PCR_ALLOWED_HOSTS` | No | `localhost,127.0.0.1,[::1]` | Comma-separated Django `ALLOWED_HOSTS`. |

### Local database

SQL Server is the target backend, but local access to it is currently blocked by a
permissions issue, so `PCR_DATABASE_URL` in `.env` points at one of two local
alternatives instead:

- **Company laptop — SQLite** (default in `.env.example`, no extra setup):

  ```bash
  uv run poe db:upgrade
  uv run poe serve
  ```

- **Personal machine — Postgres**, via Docker Compose (`compose.yaml`). Set the
  Postgres `PCR_DATABASE_URL` and `PCR_POSTGRES_*` values in `.env`, then:

  ```bash
  uv run poe pg:up       # starts postgres, waits for it to be healthy
  uv run poe db:upgrade
  uv run poe serve
  ```

Schema changes go through Alembic migrations, not manual DDL — after changing a
model in `persistence/models.py`, run `uv run poe db:revision -m "..."` and
commit the generated file under `persistence/migrations/versions/`. This PCR
schema is entirely separate from Django's own `db.sqlite3`, which only backs
Django's built-in apps (see CLAUDE.md, "Two separate databases").

## Architecture at a glance

Layered/hexagonal: **domain → application → persistence**, with Django (`web`, `config`) as a
thin delivery layer. Dependencies point inward — the domain layer has no Django or SQLAlchemy
imports.

```text
src/pcr_governance_app/
  domain/        Pure business logic: PCR/approval/audit models, the status state machine,
                 the approval engine. No I/O.
  application/   Use-case services (create/submit/withdraw a PCR, approve/reject a workflow,
                 queries) built on a UnitOfWork protocol.
  persistence/   The only SQLAlchemy-aware layer: ORM models, mappers to/from the domain
                 models, repositories, and Alembic migrations.
  web/           Django views, forms, presenters and templates.
  config/        Django settings, URLconf, WSGI/ASGI entry points.
tests/           Test suite
```

See [CLAUDE.md](CLAUDE.md) for the full architecture writeup, and
[CONTRIBUTING.md](CONTRIBUTING.md) for where new code should go.

## Troubleshooting

- **"Configuration Error" page (HTTP 503)** — `PCR_DATABASE_URL` isn't set. Check `.env`.
- **"A current user is required to create a PCR."** — set a current user in the header first.
- **Postgres container never becomes healthy** — check `docker compose logs postgres` and that
  `PCR_POSTGRES_*` are set in `.env`.
- **Schema errors / missing tables** — run `uv run poe db:upgrade` to apply pending Alembic
  migrations, or `uv run poe db:check` to see whether models and migrations have drifted.

## Repository

<https://github.com/Sandsy09/pcr-governance-app>

Clone with `git clone https://github.com/Sandsy09/pcr-governance-app.git`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see
[SECURITY.md](SECURITY.md) — do not open a public issue.

## License

See [LICENSE](LICENSE).
