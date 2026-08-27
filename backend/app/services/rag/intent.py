"""Query intent detection for RAG pipeline."""

import logging
import re

from app.models.schemas import QueryIntent

logger = logging.getLogger(__name__)


def detect_query_intent(query: str) -> QueryIntent:
    """
    Detect whether a query is a simple factual question or requires deep analysis.

    FACTUAL queries get concise, direct answers (e.g., "what was the date?")
    ANALYTICAL queries get structured analysis (e.g., "what's the best strategy?")
    """
    query_lower = query.lower().strip()

    # Patterns that indicate FACTUAL (simple lookup) questions
    factual_patterns = [
        # Direct fact questions
        r"^(what|when|where|who|which)\s+(is|was|are|were|did)\s+the\s+",
        r"^(what|when|where|who|which)\s+(is|was|are|were)\s+",
        r"^what\s+(date|time|year|month|day|name|number|amount|address|location)",
        r"^when\s+(did|was|were|is)",
        r"^where\s+(did|was|were|is)",
        r"^who\s+(is|was|are|were|did)",
        r"^how\s+(many|much|long|old|often)",
        r"^(is|are|was|were|does|do|did|has|have|had)\s+",
        r"^(list|name|identify|find|show|give me|tell me)\s+(the|all|each)",
        # Specific fact lookups
        r"(what|the)\s+(date|deadline|amount|price|cost|number|name|address|party|parties)",
        r"(filed|argued|decided|signed|executed|effective)\s+(on|date)",
        # Yes/no questions
        r"^(is|are|was|were|does|do|did|can|could|will|would|should|has|have)\s+\w+\s+(a|the|this|that|any)",
    ]

    # Patterns that indicate ANALYTICAL (complex) questions
    analytical_patterns = [
        # Strategy and advice
        r"(strategy|strategies|strategic|approach|approaches)",
        r"(recommend|recommendation|suggestions?|advise|advice)",
        r"(should\s+(we|i|they|the)|what\s+should)",
        r"(best|better|optimal|ideal)\s+(way|approach|strategy|option|course)",
        # Analysis requests
        r"(analyze|analysis|assess|assessment|evaluate|evaluation)",
        r"(compare|comparison|contrast|difference|similarities)",
        r"(strengths?|weaknesses?|pros?\s+and\s+cons?|advantages?|disadvantages?)",
        r"(risk|risks|implications?|consequences?|impact)",
        r"(argument|arguments|position|positions|theory|theories)",
        # Deep reasoning
        r"(why|how\s+can|how\s+should|how\s+would|how\s+do\s+we)",
        r"(what\s+are\s+the\s+(key|main|primary|important))",
        r"(what\s+if|hypothetically|assuming|suppose)",
        r"(explain|elaborate|discuss|describe\s+in\s+detail)",
        r"(draft|write|prepare|create)\s+(a|an|the)",
        # Legal analysis
        r"(legal\s+basis|grounds?|precedent|authority|authorities)",
        r"(counterargument|rebuttal|response\s+to|defense)",
        r"(likely|likelihood|probability|chances?|odds)",
        r"(win|lose|prevail|succeed|outcome)",
    ]

    # Check for analytical patterns first (they override factual)
    for pattern in analytical_patterns:
        if re.search(pattern, query_lower):
            logger.debug(f"[Intent] ANALYTICAL - matched pattern: {pattern}")
            return QueryIntent.ANALYTICAL

    # Check for factual patterns
    for pattern in factual_patterns:
        if re.search(pattern, query_lower):
            logger.debug(f"[Intent] FACTUAL - matched pattern: {pattern}")
            return QueryIntent.FACTUAL

    # Check query length - very short queries are often factual lookups
    word_count = len(query.split())
    if word_count <= 8:
        logger.debug(f"[Intent] FACTUAL - short query ({word_count} words)")
        return QueryIntent.FACTUAL

    # Default to analytical for longer, complex queries
    logger.debug(f"[Intent] ANALYTICAL - default for longer query ({word_count} words)")
    return QueryIntent.ANALYTICAL
