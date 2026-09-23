# Security Policy

## Supported versions

There are no tagged releases yet — the `main` branch is the only supported line, and only the
most recently deployed build receives fixes.

## Reporting a vulnerability

Do not open a public issue.

Report privately through
[GitHub's private vulnerability reporting](https://github.com/Sandsy09/pcr-governance-app/security/advisories/new).
Include what you found, the steps to reproduce it, and its impact if you can. You should get an
acknowledgement within a few business days.

## Current security model and known limitations

This app is early-stage; treat it as suitable for trusted local/internal use only, not as
production-hardened, until the items below are addressed:

- **There is no authentication.** The "current user" shown in the header
  (`web/context_processors.py`, `web/views.set_actor`) is a free-text string a visitor sets for
  themselves, stored in a signed session cookie. The audit trail attributes actions to this
  value, so it identifies who *claimed* to act, not a verified identity. Do not expose a
  deployment of this app beyond trusted users without adding real authentication first, and see
  `CLAUDE.md`/`CONTRIBUTING.md` before building authorization on top of the current actor.
- **`DEBUG` defaults to on** (`PCR_DEBUG`, default `true` in `config/settings.py`), and the
  Django `SECRET_KEY` falls back to an insecure value committed in that file if
  `PCR_DJANGO_SECRET_KEY` isn't set. `SECRET_KEY` also signs the session and message cookies (see
  `SESSION_ENGINE`/`MESSAGE_STORAGE`), so an unset key means those are forgeable.
- **`/admin/` is mounted** (Django admin) but not used for PCR data — PCR/approval/audit data is
  entirely outside Django's ORM.
- CSRF protection is enabled (`CsrfViewMiddleware`), and the "set current user" redirect
  validates its `next` target with `url_has_allowed_host_and_scheme` before following it.

### Deployment hardening checklist

Before running this app anywhere other than a trusted local/internal box:

- Set `PCR_DJANGO_SECRET_KEY` to a real secret, `PCR_DEBUG=false`, and `PCR_ALLOWED_HOSTS` to the
  real host(s).
- Serve it behind TLS.
- Use a least-privilege database account in `PCR_DATABASE_URL`, scoped to only the PCR schema.
- Run `python manage.py check --deploy` and address what it flags.
- Keep `.env` out of version control (it already is — see below).

## Handling secrets

Never commit real secrets or credentials. The repository's ignore rules already cover `.env` and
`.env.*`, common private-key extensions (`*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.keystore`), and
conventional SSH/token filenames (`id_rsa`, `credentials.json`). `.pre-commit-config.yaml` also
installs the `detect-private-key` hook from `pre-commit-hooks`, which scans staged files for
private key material before each commit — run `uv run pre-commit install` (see
[CONTRIBUTING.md](CONTRIBUTING.md)) so it's actually active locally. Local Postgres
(`compose.yaml`) binds only to `127.0.0.1`, and its credentials come from `.env`, never from the
compose file itself.

Ignore rules and the pre-commit hook are not a substitute for scanning: neither checks git
history, and the hook only catches recognizable private-key formats, not arbitrary API keys or
tokens embedded in code, logs, or commit messages. For broader coverage, add an optional
secret-scanning tool (for example, [gitleaks](https://github.com/gitleaks/gitleaks)) through a
selected capability, or enable your Git host's native secret scanning where available. Neither is
enabled by default.

## Dependency security

Dependencies are pinned via `uv.lock` and CI enforces that the lockfile matches declared
dependencies (`uv run poe lock:check`). Dependabot opens weekly pull requests for outdated `uv`
dependencies and GitHub Actions (`.github/dependabot.yml`). Workflow actions are pinned to full
commit SHAs (`.github/workflows/ci.yml`), not floating tags, so a compromised tag can't silently
change what CI runs.
