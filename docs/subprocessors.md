# Data Flows & Subprocessors

CaseCite is self-hosted: the firm runs the application and database on its own
infrastructure. There is no CaseCite-operated SaaS backend, and document content is
never sent to a CaseCite-controlled service. However, several features call
third-party APIs. This document lists exactly what leaves the deployment boundary
so a firm's InfoSec team can assess and control it.

> Note: document content **is** transmitted to the
> configured LLM provider (under the firm's own API key / self-hosted endpoint)
> when AI features are used. It does not pass through any CaseCite-operated SaaS.

## What data can leave the boundary

| Recipient | Purpose | Data sent | How to control |
|-----------|---------|-----------|----------------|
| **OpenAI** (or OpenAI-compatible endpoint) | Embeddings, chat/analysis | Prompts + retrieved document excerpts, uploaded document text | BYOK; unset `OPENAI_API_KEY`; or point `OPENAI_BASE_URL` at a self-hosted model (Ollama/vLLM) to keep inference on-prem |
| **Anthropic** | Chat/analysis | Prompts + document excerpts | BYOK; unset `ANTHROPIC_API_KEY` |
| **Google (Gemini)** | Chat/analysis (per-user key) | Prompts + document excerpts | Per-user BYOK; do not configure |
| **Voyage AI / Cohere** | Optional embeddings/reranking | Document text chunks | Optional; unset the key |
| **CourtListener** | Case-law / docket / judge lookups | Search queries, citations (no client documents) | Optional token; feature works without |
| **SendGrid** | Transactional email (password reset) | Recipient email address, reset link | Optional; unset `SENDGRID_API_KEY` |

## Keeping data on-premises

- **Self-hosted inference:** set `OPENAI_BASE_URL` to an in-VPC OpenAI-compatible
  server (Ollama, vLLM, LM Studio) so prompts and document text never leave the
  network. Admins can set this at runtime (Integrations → Local LLM).
- **Disable outbound features:** leave provider keys unset to hard-disable those
  calls (the app fails closed for that feature rather than sending data).
- **Egress control:** run the container behind an egress allowlist limited to the
  providers you intentionally use.

## HIPAA / heightened-confidentiality mode

`HIPAA_ENFORCEMENT_ENABLED=true` with `APPROVED_AI_PROVIDERS` restricts AI calls
to an explicit provider allowlist. Combine with self-hosted inference for
workloads that must not egress.

## Where data rests

All persistent data (documents, vector store, database, encrypted key store,
audit logs) lives on the deployment's own `data/` volume / database. That volume
**must be encrypted at rest** (LUKS/dm-crypt or the cloud provider's encrypted
disk) — it holds privileged client data in plaintext at the filesystem level.
