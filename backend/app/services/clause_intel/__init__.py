"""
Clause Intelligence (Phase 1)

Real domain logic for clause classification, missing-clause detection,
and deviation detection. Pure rule + embedding work — LLM is only used
to *explain* findings, never to detect them.
"""

from app.services.clause_intel.service import clause_intel_service

__all__ = ["clause_intel_service"]
