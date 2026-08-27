# Roadmap

## Current
- Research chat over the firm's documents with verified citations and a case-law guard
- Contract analysis, redlining as native Word tracked changes, and long-document drafting
- Strategy briefs with quote-verified authorities (API; UI in progress)
- Judge intelligence, citation check, and case-law tools backed by CourtListener
- Matter-scoped sharing, tamper-evident audit trail, BYOK keys encrypted at rest
- Multi-provider RAG (OpenAI, Anthropic, Voyage, Cohere, Google)

## Next
- Matters UI (the API is complete and already scopes documents, chats, and workspaces)
- Password-reset page in the frontend (backend flow and email are complete)
- Azure AD SSO sign-in flow in the frontend (backend exchange is complete)
- Preserve run-level formatting from the source .docx in redline exports
- "AI-generated — verify before relying" notices on every generated artifact and export
- Enforceable MFA policy per role; forced rotation of admin-issued temporary passwords

## Future
- External anchoring of the audit-chain head (object-lock bucket or SIEM)
- Multi-worker / multi-replica deployments (sessions and document registry in Redis/Postgres)
- Integration with additional court e-filing systems
- Multi-language document support
