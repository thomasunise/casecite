"""
Contract Analysis (Phase 2)

Real domain logic:
- party graph resolver
- structured obligation extractor (regex + spaCy-style passes)
- date / period extractor → feeds existing deadline calculator
- rule-based risk scoring
- defined-terms checker

LLM is used only for fallback structured extraction with strict JSON schema
validation, never for ad-hoc analysis.
"""

from app.services.contract_analysis.service import contract_analysis_service

__all__ = ["contract_analysis_service"]
