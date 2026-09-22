# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Do not open a public issue.
Use your repository host's private vulnerability reporting feature, if it has
one, to report privately.

You should get an acknowledgement within a few business days.

## GitHub security advisories

Report privately through
[GitHub's private vulnerability reporting](https://github.com/Sandsy09/pcr-governance-app/security/advisories/new).

## Handling secrets

Never commit real secrets or credentials. The repository's ignore rules
already cover `.env` and `.env.*`, common private-key extensions (`*.pem`,
`*.key`, `*.p12`, `*.pfx`, `*.keystore`), and conventional SSH/token
filenames (`id_rsa`, `credentials.json`). Foundation does not install a
`detect-private-key` hook. Ignore rules are the last line of
defence, not detection: they do not scan history or catch secrets embedded in
code or logs.

For broader coverage, add an optional secret-scanning tool (for example,
[gitleaks](https://github.com/gitleaks/gitleaks)) through a selected
capability, or enable your Git host's native scanning where available.
Neither is enabled by default.
