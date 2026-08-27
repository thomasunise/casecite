"""LLM generation and context building for RAG pipeline."""

import logging
from typing import Any

from app.models.schemas import QueryIntent
from app.services.llm_clients import openai_chat
from app.services.rag.prompt_safety import untrusted_block

logger = logging.getLogger(__name__)


def build_context_with_case_law(
    doc_results: list[dict[str, Any]], case_law_results: list[dict[str, Any]]
) -> str:
    """Build context string from both document and case law results.

    Every chunk and opinion excerpt is third-party text, so each is wrapped
    in an ``untrusted_block`` — the model is told (via the system prompt's
    UNTRUSTED_CONTENT_RULE) that whatever those blocks say is data.
    """
    context_parts = []

    if doc_results:
        context_parts.append("=== FROM YOUR DOCUMENTS ===\n")
        for i, result in enumerate(doc_results):
            source = result.get("metadata", {}).get("filename", "Unknown")
            text = result.get("text", "")
            label = f"Document {i + 1}: {source}"
            context_parts.append(f"[{label}]\n{untrusted_block(label, text)}\n")

    if case_law_results:
        context_parts.append("\n=== FROM CASE LAW (CourtListener) ===\n")
        for i, result in enumerate(case_law_results):
            metadata = result.get("metadata", {})
            case_name = metadata.get("filename", "Unknown Case")
            citation = metadata.get("citation", "")
            court = metadata.get("court", "")
            text = result.get("text", "")
            label = f"Case {i + 1}: {case_name}"
            context_parts.append(
                f"[{label}]\nCourt: {court}\nCitation: {citation}\n{untrusted_block(label, text)}\n"
            )

    return "\n---\n".join(context_parts)


def get_model_max_tokens(model_name: str, intent: QueryIntent | None = None) -> int:
    """Get maximum output tokens for a model, adjusted by query intent."""
    # Factual queries: cap at 500 tokens - they should be brief
    if intent == QueryIntent.FACTUAL:
        return 500

    model_lower = model_name.lower()
    if "gpt-5" in model_lower:
        return 32768
    elif "gpt-4o" in model_lower:
        return 16384
    elif "gpt-4-turbo" in model_lower or "gpt-4" in model_lower:
        return 4096
    elif "claude-opus" in model_lower or "claude-sonnet-4" in model_lower or "fable" in model_lower:
        return 32768
    elif (
        "claude-3-5" in model_lower or "claude-3.5" in model_lower or "claude-haiku" in model_lower
    ):
        return 8192
    elif "claude" in model_lower:
        return 4096
    elif "gemini" in model_lower:
        return 8192
    elif "o1" in model_lower or "o3" in model_lower:
        return 32768
    else:
        return 4096


async def call_llm(
    openai_client,
    anthropic_client,
    gemini_model,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float = 0.1,
) -> str:
    """Call the appropriate LLM provider and return response content.

    Tries Claude first if model contains 'claude', then Gemini, then OpenAI.
    Raises ValueError if no LLM is configured.
    """
    if "claude" in model.lower() and anthropic_client:
        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    elif "gemini" in model.lower() and gemini_model:
        import asyncio

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await asyncio.to_thread(gemini_model.generate_content, full_prompt)
        return response.text
    elif openai_client:
        response = await openai_chat(
            openai_client,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    else:
        raise ValueError(
            "No LLM configured. Please provide an API key in Settings, "
            "or set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable."
        )
