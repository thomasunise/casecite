import logging
import os
import secrets
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Prefixes that indicate a placeholder value, not a real secret  # nosec B105
_PLACEHOLDER_PREFIXES = ("change-me", "REPLACE_WITH", "REPLACE-ME", "your-", "sk-your")

# Settings removed with the public-demo posture; still present in older .env files.
_REMOVED_SETTINGS = frozenset(
    {
        "demo_mode",
        "demo_daily_query_limit",
        "demo_max_documents",
        "demo_account_email",
        "sales_email",
    }
)


class Settings(BaseSettings):
    # App
    app_name: str = "CaseCite RAG"
    app_display_name: str = "CaseCite"
    debug: bool = False
    environment: str = "development"
    api_prefix: str = "/api/v1"

    # Branding / Contact emails (override for white-label deployments)
    noreply_email: str = "noreply@casecite.com"
    support_email: str = "support@casecite.com"
    security_email: str = "security@casecite.com"

    # Explicit flag to disable CSRF (must be True WITH debug=True to skip CSRF)
    csrf_disabled: bool = False

    # Security - MUST be set in production via environment variable
    secret_key: str = ""  # Will be validated on startup
    access_token_expire_minutes: int = 60  # 1 hour (reduced from 24 for security)

    # Self-service registration. Default OFF in production: an internet-reachable
    # instance with open registration lets anyone self-provision a full-access
    # account. Enable deliberately (ALLOW_REGISTRATION=true) for trusted networks.
    # In debug (local development), registration is always open for convenience.
    allow_registration: bool = False
    # Optional token required to create the FIRST (admin) account on a fresh
    # install. Set REGISTRATION_BOOTSTRAP_TOKEN to prevent an attacker who reaches
    # the instance before you from seizing the first-user-is-admin slot. When
    # unset, the first registration is allowed (bootstrap before exposing publicly).
    registration_bootstrap_token: str = ""

    # Frontend URL for password reset emails (e.g., https://app.casecite.com)
    frontend_url: str = ""

    # Encryption salt - generated per deployment, stored in .env
    encryption_salt: str = ""  # Will be auto-generated if not set
    # Previous encryption salts for key rotation (comma-separated)
    # Move old ENCRYPTION_SALT here when rotating to a new salt
    encryption_salt_previous: str = ""

    # Email service (SendGrid)
    sendgrid_api_key: str | None = None

    # Redis for session/token management (required for production)
    redis_url: str | None = None  # e.g., redis://localhost:6379/0
    redis_socket_timeout: float = 5.0

    # Session IP binding (rejects requests from a different IP than login).
    # Default OFF: behind a reverse proxy (Coolify/Traefik/nginx) or on mobile
    # networks the client IP varies between requests, which would log users out
    # on refresh. Opt in with ENFORCE_SESSION_IP_BINDING=true only when the
    # client IP is guaranteed stable end-to-end.
    enforce_session_ip_binding: bool = False

    # Database (PostgreSQL for production, SQLite for development)
    # Set DATABASE_URL for production: postgresql+asyncpg://user:pass@host:5432/casecite
    database_url: str | None = None  # Defaults to SQLite if not set

    @model_validator(mode="before")
    @classmethod
    def _drop_removed_settings(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Ignore settings removed with the public-demo posture (runs before freeze).

        Earlier releases shipped these keys in .env.example, so existing .env
        files still carry them. pydantic-settings rejects unknown dotenv keys,
        which would turn a routine upgrade into a startup crash; drop exactly
        these keys with a warning instead. The only development flag is DEBUG.
        """
        for key in [k for k in data if str(k).lower() in _REMOVED_SETTINGS]:
            data.pop(key)
            name = str(key).upper()
            hint = " (for local development set DEBUG=true)" if name == "DEMO_MODE" else ""
            logger.warning(
                "%s was removed in this release and is ignored — delete it from .env%s",
                name,
                hint,
            )
        return data

    @model_validator(mode="before")
    @classmethod
    def _generate_dev_secrets(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Auto-generate secrets for local development (DEBUG=true; runs before freeze)."""
        debug = data.get("debug", False)
        # Handle raw string values from environment variables
        if isinstance(debug, str):
            debug = debug.lower() in ("true", "1", "yes")
        if not debug:
            return data

        # Persist auto-generated dev secrets to the data dir so they survive
        # restarts. Without this, every container restart regenerates the keys,
        # invalidating all issued tokens/sessions (users get logged out and have
        # to sign in again). Explicit env vars always take precedence.
        import json
        from pathlib import Path

        data_dir = Path(data.get("upload_dir") or "./data/uploads").parent
        secrets_file = data_dir / ".instance_secrets.json"
        persisted: dict[str, str] = {}
        try:
            if secrets_file.exists():
                loaded = json.loads(secrets_file.read_text())
                if isinstance(loaded, dict):
                    persisted = {k: str(v) for k, v in loaded.items()}
        except (OSError, ValueError):
            persisted = {}

        changed = False

        def _resolve(field: str, nbytes: int) -> None:
            nonlocal changed
            val = data.get(field, "")
            if val and not any(val.startswith(p) for p in _PLACEHOLDER_PREFIXES):  # nosec B105
                return  # explicitly set via env — leave it untouched
            if persisted.get(field):
                data[field] = persisted[field]
                return
            generated = secrets.token_hex(nbytes)
            data[field] = generated
            persisted[field] = generated
            changed = True

        _resolve("secret_key", 32)
        _resolve("encryption_salt", 16)
        _resolve("audit_hmac_key", 32)

        if changed:
            logger.warning(
                "SECRET_KEY/ENCRYPTION_SALT/AUDIT_HMAC_KEY not set — auto-generated "
                "for development (DEBUG=true). Set them as env vars for production."
            )
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                secrets_file.write_text(json.dumps(persisted))
                try:
                    os.chmod(secrets_file, 0o600)
                except OSError:
                    pass
            except OSError as e:
                logger.warning("Could not persist instance secrets to %s: %s", secrets_file, e)
        return data

    @field_validator("openai_api_key", "anthropic_api_key", "voyage_api_key", mode="before")
    @classmethod
    def _ignore_garbage_keys(cls, v, info):
        """Treat a mangled env key as NO key (runs before the frozen model is built).

        A lone "#" (a commented .env line pasted into an env panel) or similar
        debris must not masquerade as a configured provider — it makes every
        fallback call fail with a baffling provider 401 instead of a clear
        "no key configured", and breaks BYOK-only instances whose real keys
        live in the app's Settings. A real key never starts with "#" and is
        never this short.
        """
        if v is None:
            return v
        val = str(v).strip()
        if val and (val.startswith("#") or len(val) <= 2):
            logger.warning(
                f"{info.field_name.upper()} is set to an obviously invalid value "
                f"({val[:4]!r}…) — ignoring it. Remove the stray value from the "
                "environment, or set a real key."
            )
            return None
        return v

    @model_validator(mode="after")
    def _validate_security_settings(self) -> "Settings":
        """Validate security settings (read-only, model is frozen after this)."""
        # Validate SECRET_KEY (nosec B105 - checking for placeholder, not storing secret)
        if not self.secret_key or any(self.secret_key.startswith(p) for p in _PLACEHOLDER_PREFIXES):  # nosec B105
            raise ValueError(
                "SECURITY ERROR: SECRET_KEY must be set for production. "
                "Generate one with: openssl rand -hex 32"
            )
        elif len(self.secret_key) < 32:
            raise ValueError(
                "SECURITY ERROR: SECRET_KEY must be at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )

        # Validate encryption salt
        if not self.encryption_salt or any(
            self.encryption_salt.startswith(p) for p in _PLACEHOLDER_PREFIXES
        ):
            raise ValueError(
                "SECURITY ERROR: ENCRYPTION_SALT must be set for production. "
                "Generate one with: openssl rand -hex 16"
            )

        # Validate audit HMAC key
        if not self.audit_hmac_key or any(
            self.audit_hmac_key.startswith(p) for p in _PLACEHOLDER_PREFIXES
        ):
            raise ValueError(
                "SECURITY ERROR: AUDIT_HMAC_KEY must be set for production. "
                "Generate one with: openssl rand -hex 32"
            )

        # Enforce Redis for production
        if not self.redis_url and not self.debug:
            raise ValueError(
                "CONFIGURATION ERROR: REDIS_URL must be set for production. "
                "Redis is required for distributed rate limiting and session management. "
                "Set REDIS_URL=redis://host:6379/0 for production deployments."
            )

        # Warn when DEBUG disables CSRF protection
        if self.debug:
            logger.warning(
                "DEBUG=true disables CSRF protection. "
                "Ensure DEBUG is false in production deployments."
            )

        # Enforce DATABASE_URL for production
        if not self.database_url and not self.debug:
            raise ValueError(
                "CONFIGURATION ERROR: DATABASE_URL must be set for production. "
                "SQLite is not suitable for production workloads. "
                "Set DATABASE_URL=postgresql+asyncpg://user:pass@host/db for production."
            )

        # Data-at-rest: derived privileged content (vector chunks, extracted
        # clause text, chat history) is stored unencrypted. Require the operator
        # to confirm the data volume is encrypted before serving production
        # traffic. Fail closed — a silent warning is not a control.
        if not self.debug and not self.disk_encryption_acknowledged:
            raise ValueError(
                "SECURITY ERROR: derived privileged content (vector chunks, extracted "
                "clause text, chat history) is stored UNENCRYPTED at rest. Enable "
                "full-disk/volume encryption on the data volume (LUKS, BitLocker, or "
                "FileVault), then set DISK_ENCRYPTION_ACKNOWLEDGED=true to confirm. "
                "This gate exists because a stolen disk or laptop would otherwise "
                "expose the plaintext document corpus."
            )

        # A server-level AI key is OPTIONAL: this is a BYOK product — users
        # supply their own keys in Settings, stored encrypted per user. The
        # server env key is only a fallback for instances that want one.
        if not (self.openai_api_key or self.anthropic_api_key):
            logger.info(
                "No server-level AI provider key configured — running BYOK-only. "
                "Users must add their own API keys in Settings; background jobs "
                "use each user's stored keys."
            )

        # Production mode validation summary
        if not self.debug:
            missing_recommended = []
            if not self.redis_url:
                missing_recommended.append("REDIS_URL")
            if not self.database_url:
                missing_recommended.append("DATABASE_URL")
            if missing_recommended:
                logger.warning(
                    f"Production deployment missing recommended configs: {', '.join(missing_recommended)}. "
                    "Some features may not work correctly."
                )

        return self

    # OpenAI
    openai_api_key: str | None = None
    openai_embedding_model: str = (
        "text-embedding-3-small"  # current; text-embedding-3-large for higher quality
    )
    openai_chat_model: str = "gpt-5.5"  # OpenAI flagship (2026)
    openai_utility_model: str = (
        "gpt-5.4-mini"  # cheaper model for high-volume utility/extraction calls
    )
    # Point the OpenAI-compatible client at a custom endpoint to use local/open models
    # (Ollama http://host:11434/v1, LM Studio, vLLM) or hosted OSS gateways (Together,
    # Groq, OpenRouter). Leave unset for OpenAI. Also editable at runtime via the admin UI.
    openai_base_url: str | None = None
    # Context window (tokens) of the chat model, when its name doesn't say — custom
    # or local endpoints. Long-document drafting budgets reference material against
    # it. Unset: inferred from the model name (gpt-5 → 400k, gpt-4o → 128k, ...).
    llm_context_window: int | None = None

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = (
        "claude-opus-4-8"  # current Anthropic flagship (use the bare ID, no date suffix)
    )

    # Google Gemini (used via per-user keys)
    gemini_model: str = "gemini-3.1-pro-preview"  # current Gemini Pro

    # Voyage AI (Legal Embeddings) - Optional
    voyage_api_key: str | None = None
    # Default to OpenAI embeddings. Set to voyage-law-2 (legal-optimized, still recommended for
    # legal text) or a voyage-4 model with a Voyage key. NOTE: changing the embedding model changes
    # vector dimensions/space and requires re-indexing existing documents.
    embedding_model: str = "text-embedding-3-small"

    # Cohere (Alternative Embeddings)
    cohere_api_key: str | None = None

    # CourtListener (Free Case Law)
    courtlistener_api_token: str | None = None  # Optional, but recommended for higher rate limits

    # Vector Database
    vector_db: str = "chroma"  # "chroma" or "pinecone"
    chroma_persist_dir: str = "./data/chroma"
    pinecone_api_key: str | None = None
    pinecone_environment: str = "us-east-1"
    pinecone_index_name: str = "casecite-legal"

    # RAG Settings - Enterprise Configuration
    chunk_size: int = 512
    chunk_overlap: int = 128
    top_k: int = 10
    # Cosine-similarity floor for retrieval. SCALE IS MODEL-DEPENDENT: with
    # text-embedding-3-* a relevant chunk typically scores 0.30-0.50, so a
    # threshold above ~0.5 silently discards nearly every real match and the
    # product reads as "your documents don't exist". 0.25 keeps junk out
    # without strangling recall.
    similarity_threshold: float = 0.25
    rerank_enabled: bool = True  # Enable cross-encoder reranking
    rerank_top_k: int = 20  # Retrieve more, then rerank to top_k
    hybrid_search_enabled: bool = True  # Combine semantic + keyword search
    keyword_weight: float = 0.3  # Weight for BM25 keyword matching

    # API Resilience Settings
    api_retry_attempts: int = 3
    api_retry_delay: float = 1.0  # Base delay in seconds
    # Per-request timeout (seconds) for every LLM/embedding SDK client, with
    # two SDK retries on top. Long contract reviews and drafting sections can
    # legitimately take a minute or more to produce a first byte; 30s caused
    # spurious retries. Override with API_TIMEOUT.
    api_timeout: float = 180.0
    circuit_breaker_threshold: int = 5  # Failures before circuit opens
    circuit_breaker_timeout: float = 60.0  # Seconds before retry

    # Connector: Google Drive
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # GOOGLE_REDIRECT_URI is required for production - no localhost fallback
    google_redirect_uri: str = os.environ.get("GOOGLE_REDIRECT_URI", "")

    # Connector: Microsoft (OneDrive/SharePoint)
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant_id: str | None = None
    # MICROSOFT_REDIRECT_URI is required for production - no localhost fallback
    microsoft_redirect_uri: str = os.environ.get("MICROSOFT_REDIRECT_URI", "")
    # Azure AD SSO account lifecycle. Roles always come from the local users
    # row; these only govern what happens on a first-time SSO login.
    azure_sso_auto_provision: bool = True  # False: only admin-invited users can sign in
    azure_sso_default_role: str = "viewer"  # role for auto-provisioned users (never admin)

    # Connector: Box
    box_client_id: str | None = None
    box_client_secret: str | None = None
    # BOX_REDIRECT_URI is required for production - no localhost fallback
    box_redirect_uri: str = os.environ.get("BOX_REDIRECT_URI", "")

    # Connector: NetDocuments
    netdocuments_client_id: str | None = None
    netdocuments_client_secret: str | None = None
    # NETDOCUMENTS_REDIRECT_URI is required for production - no localhost fallback
    netdocuments_redirect_uri: str = os.environ.get("NETDOCUMENTS_REDIRECT_URI", "")
    # Region hosts — US vault defaults; EU tenants use vault.eu.netdocuments.com /
    # api.eu.netdocuments.com, AU uses the .au equivalents.
    netdocuments_vault_host: str = "https://vault.netvoyage.com"
    netdocuments_api_host: str = "https://api.vault.netvoyage.com"

    # Connector: iManage
    imanage_client_id: str | None = None
    imanage_client_secret: str | None = None
    imanage_base_url: str | None = None
    # IMANAGE_REDIRECT_URI is required for production - no localhost fallback
    imanage_redirect_uri: str = os.environ.get("IMANAGE_REDIRECT_URI", "")

    # Connector: Filevine (API key + secret; session handshake, not OAuth)
    filevine_api_key: str | None = None
    filevine_api_secret: str | None = None
    filevine_base_url: str = "https://api.filevine.io"

    # Connector: Clio (EU tenants set CLIO_BASE_URL=https://eu.app.clio.com)
    clio_client_id: str | None = None
    clio_client_secret: str | None = None
    clio_base_url: str = "https://app.clio.com"
    # CLIO_REDIRECT_URI is required for production - no localhost fallback
    clio_redirect_uri: str = os.environ.get("CLIO_REDIRECT_URI", "")

    # Connector: Dropbox
    dropbox_app_key: str | None = None
    dropbox_app_secret: str | None = None
    # DROPBOX_REDIRECT_URI is required for production - no localhost fallback
    dropbox_redirect_uri: str = os.environ.get("DROPBOX_REDIRECT_URI", "")

    # ============================================
    # FILE PICKER APIs (No OAuth Verification Required)
    # These use limited scopes that don't need Google/Microsoft verification
    # ============================================

    # Google Picker API - Get from Google Cloud Console (APIs & Services > Credentials)
    # Creates an API key (not OAuth client) for the Picker
    google_api_key: str | None = None  # API key for Google Picker
    google_app_id: str | None = None  # Project number from Google Cloud Console

    # Microsoft OneDrive Picker - Uses same client_id but different scope
    # No additional config needed - uses microsoft_client_id above

    # Box UI Elements - Uses same client_id
    # No additional config needed - uses box_client_id above

    # Dropbox Chooser - Uses app key (same as dropbox_app_key above)

    # Job Queue
    job_result_ttl: int = 1800  # 30 min completed results
    job_failed_ttl: int = 86400  # 24h failed jobs
    job_dead_letter_ttl: int = 604800  # 7d dead letter
    job_max_result_size: int = 1_048_576  # 1MB max result in Redis
    job_shutdown_timeout: int = 30  # Seconds to drain on shutdown
    # Max jobs executing concurrently. Bounds memory/connection use so a burst of
    # submissions (LLM + CourtListener fan-out) can't exhaust the API process.
    job_max_concurrency: int = 5

    # Storage
    upload_dir: str = "./data/uploads"
    max_upload_size: int = 100 * 1024 * 1024  # 100MB

    # Data-at-rest acknowledgement. Uploaded originals are app-encrypted
    # (AES-256-GCM), but DERIVED privileged text — vector chunks in the Chroma
    # store, extracted clause text, and chat history in the DB — is stored in
    # cleartext. On a single-tenant self-host that is acceptable ONLY when the
    # underlying volume is encrypted (LUKS / BitLocker / FileVault), otherwise a
    # stolen disk or laptop leaks the whole corpus. The app cannot detect
    # full-disk encryption, so production requires the operator to consciously
    # confirm it here. Set DISK_ENCRYPTION_ACKNOWLEDGED=true after enabling FDE.
    disk_encryption_acknowledged: bool = False

    # HIPAA Enforcement (dormant unless explicitly enabled)
    hipaa_enforcement_enabled: bool = False
    approved_ai_providers: list[str] = []  # e.g., ["openai", "anthropic"]

    # Dedicated HMAC key for audit chain hashing (separate from secret_key)
    audit_hmac_key: str = ""
    # Set to the OLD key when rotating audit_hmac_key so entries signed under it
    # still verify at startup; clear it once those logs age out of retention.
    audit_hmac_key_previous: str = ""

    # Halt startup if audit chain integrity is broken (tamper detection)
    audit_halt_on_tampering: bool = True

    # Audit-log retention: JSONL files older than this are gzip-compressed; files
    # older than 2x this are deleted. A daily background task applies this.
    audit_retention_days: int = 90

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],  # Check parent directory first, then current
        env_file_encoding="utf-8",
        frozen=True,
    )


settings = Settings()

# Ensure directories exist
os.makedirs(settings.chroma_persist_dir, exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)
