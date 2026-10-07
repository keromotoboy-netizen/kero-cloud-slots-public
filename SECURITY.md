# Security Policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, private endpoints, customer data, or exploitation details.

For Kero infrastructure, report the finding privately to the repository owner. Rotate any exposed credential before discussing details in a public channel.

## Repository rules

- Never commit secrets or private customer data.
- Prefer OIDC and short-lived credentials over long-lived tokens.
- GitHub Actions must use least-privilege permissions.
- Third-party Actions used by control-plane workflows should be pinned to a full commit SHA.
- Public runners may process only PUBLIC_SAFE workloads.
