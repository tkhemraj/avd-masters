# Configuration

GROKY 2.0 is deliberately simple to configure.

## Environment Variables (`.env`)

All major settings are controlled via environment variables (loaded via `pydantic-settings`).

Key areas:

- **Azure Discovery**
- **Connection Defaults** (WinRM / SSH)
- **Polling & Thresholds**
- **Storage**

See `.env.example` in the repo root for the full list with comments.

## hosts.yaml (Optional but powerful)

Use `hosts.yaml` to:
- Override credentials per host
- Add hosts not in Azure AVD
- Disable specific hosts
- Set custom connection methods

This keeps your secrets out of environment variables when needed.

## Philosophy on Config

We optimize for **one obvious way** to run the tool in development and production.

No 400-line config files. No magic.
