# Contributing

## Setup

```bash
uv sync --all-groups --locked
```

After an intentional dependency change, run `uv lock`, review the result, and
commit the updated `uv.lock`.

## Branching and pull requests

`main` is never committed to directly. Every change gets its own branch and a
pull request.

Branch names are `<type>/<short-slug>`, kebab-case, where `<type>` is a
Conventional Commits type (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`,
`ci`, `build`) -- pick the type the branch's eventual squash commit will
carry, e.g. `fix/retry-timeout` or `docs/update-readme`.

```bash
git switch -c <type>/<short-slug>
# ... commit(s) ...
git push -u origin <type>/<short-slug>
```

Open a pull request and wait for CI to pass, then **squash merge**: it keeps
one commit per change on `main`, and the squash commit's subject is what
`git log` shows afterwards, so edit it into a proper Conventional Commits
subject rather than leaving the default title.

## Before opening a pull request

```bash
uv run --locked poe check
```

Rejects lock drift, then runs formatting, lint, type checking, and tests --
the same gate automation runs.

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `chore:`, ...); a `commit-msg` hook enforces this.

## Repository

Clone with
`git clone https://github.com/Sandsy09/pcr-governance-app.git`.

Pull requests are routed for review to
`@Sandsy09/pcr-governance-app-maintainers`
through [`.github/CODEOWNERS`](.github/CODEOWNERS). Remote GitHub Actions under
`.github/workflows/` are pinned to full commit SHAs with the release tag in a
same-line comment -- keep that form when updating them.
