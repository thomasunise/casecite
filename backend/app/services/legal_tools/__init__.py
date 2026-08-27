"""
Legal Research Tools - Powered by CourtListener

Tools:
1. Case Lookup - Quick citation lookup
2. Citation Validator - Shepardize/KeyCite equivalent
3. Judge Analyzer - Judge research with ruling patterns
4. Precedent Finder - Find most-cited cases on a topic
5. Docket Search - Search court dockets
6. Oral Arguments - Browse oral argument audio
7. Citation Mapper - Visualize case connections
8. Legal Trends - Analyze how law evolves over time
"""

from ._models import (
    CaseLookupResult,
    DocketResult,
    JudgeInfo,
    JudgeRulingPattern,
    PrecedentResult,
    RulingDirection,
)
from .service import LegalToolsService

# Singleton instance
legal_tools = LegalToolsService()

__all__ = [
    "legal_tools",
    "LegalToolsService",
    "RulingDirection",
    "JudgeInfo",
    "JudgeRulingPattern",
    "CaseLookupResult",
    "PrecedentResult",
    "DocketResult",
]
