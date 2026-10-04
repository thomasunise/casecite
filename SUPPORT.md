# Support

CaseCite is self-hosted software maintained by a small team. There is no
hosted service and no support desk; this page explains where each kind of
question goes.

| You have… | Go to |
|-----------|-------|
| A security vulnerability in CaseCite | **Private** report: <https://github.com/thomasunise/casecite/security/advisories/new> — never a public issue. See [SECURITY.md](SECURITY.md). |
| A bug | [Open an issue](https://github.com/thomasunise/casecite/issues/new/choose) with steps to reproduce, the version or commit, and relevant logs (redact keys, client names and document text). |
| A feature request | [Open an issue](https://github.com/thomasunise/casecite/issues/new/choose). Check [ROADMAP.md](ROADMAP.md) first. |
| A question about deploying or operating an instance | Read [docs/deployment.md](docs/deployment.md), [docs/secret-rotation.md](docs/secret-rotation.md) and [docs/subprocessors.md](docs/subprocessors.md); if the docs don't answer it, open an issue — an unclear doc is a bug. |
| A code-of-conduct concern | See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). |
| A licensing question, a paid private install, a support contract, or hosting CaseCite for others | Contact the maintainer, [@thomasunise](https://github.com/thomasunise), through GitHub. The [license](LICENSE) (Elastic License 2.0) does not permit offering CaseCite to third parties as a managed service without a separate agreement. |

## What to expect

- Issues are triaged as time allows. There is no response-time commitment
  outside a support contract.
- Security reports are acknowledged within a few business days.
- Only the latest release is supported. Please reproduce on the current
  `main` or latest tag before reporting.

## Before you post

Never include client names, document contents, API keys, `.env` files or
unredacted audit logs in an issue. Issues are public.
