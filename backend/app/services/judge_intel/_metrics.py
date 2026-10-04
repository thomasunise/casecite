"""Metrics computation mixin for JudgeIntelService."""

import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any


class MetricsMixin:
    """Methodology definitions and advanced metrics computation."""

    def get_metrics_methodology(self) -> dict[str, dict[str, str]]:
        """
        Returns detailed methodology explanations for all computed metrics.
        Each metric includes: description, data_source, calculation, limitations, and interpretation.
        """
        return {
            "dissent_rate": {
                "name": "Dissent Rate",
                "description": "The percentage of opinions where the judge wrote a dissenting opinion, disagreeing with the majority ruling.",
                "data_source": "CourtListener opinion database - opinion_type field identifies dissents, concurrences, and majority opinions.",
                "calculation": "(Number of dissenting opinions / Total opinions with known type) * 100",
                "limitations": "Only includes opinions where the type (majority/dissent/concurrence) is recorded. Some older opinions may not have this classification. Solo judges (trial court) typically don't have dissents.",
                "interpretation": "A higher rate means the judge writes separately in disagreement more often. No benchmark is computed here; compare against other judges of the same court using their own profiles.",
            },
            "concurrence_rate": {
                "name": "Concurrence Rate",
                "description": "The percentage of opinions where the judge agreed with the outcome but wrote separately to express different reasoning.",
                "data_source": "CourtListener opinion database - opinion_type field.",
                "calculation": "(Number of concurring opinions / Total opinions with known type) * 100",
                "limitations": "Same as dissent rate - requires opinion type classification.",
                "interpretation": "Concurrences suggest nuanced legal thinking. Judges who frequently concur may have distinct interpretive approaches.",
            },
            "citation_impact_score": {
                "name": "Citation Impact Score",
                "description": "A scaled measure of how often other opinions cite this judge's opinions.",
                "data_source": "CourtListener citation counts for each opinion.",
                "calculation": "(Average citations per opinion) * ln(years since the judge's earliest opinion + 1), divided by a fixed constant (35) and capped at 5.0.",
                "limitations": "The score is NOT normalized against other judges or courts: the same fixed scale is applied to everyone, so it is not a ranking and 1.0 is not an average. Older opinions naturally accumulate more citations. Different practice areas have different citation patterns. Supreme Court opinions are cited more than district court opinions regardless of quality.",
                "interpretation": "Higher means more citations per opinion over a longer period. Compare only judges at the same court level, and read it alongside the raw counts shown with it.",
            },
            "case_disposition_time": {
                "name": "Average Case Duration",
                "description": "The average time from case filing to termination for cases assigned to this judge.",
                "data_source": "CourtListener docket data - date_filed and date_terminated fields.",
                "calculation": "Average of (date_terminated - date_filed) in days over terminated cases in the retrieved dockets. Excludes ongoing cases and durations of zero or of ten years or more.",
                "limitations": "Case complexity varies enormously. Patent cases take longer than simple contract disputes. Settlement timing is often outside judge's control. Magistrate referrals may affect timing.",
                "interpretation": "No court average is computed here. Faster isn't always better - complex cases require time.",
            },
            "case_type_expertise": {
                "name": "Case Type Distribution",
                "description": "Breakdown of case types this judge handles, showing areas of likely expertise.",
                "data_source": "CourtListener docket data - nature_of_suit field (federal) and case categorization.",
                "calculation": "Count of cases by nature of suit code, converted to percentages. Top categories highlighted.",
                "limitations": "Case assignment is often random in federal courts. High volume in an area may reflect court assignment patterns, not judge preference or expertise.",
                "interpretation": "Use to understand judge's experience with specific case types. Judges with extensive experience in your case type may be more efficient.",
            },
            "writing_complexity": {
                "name": "Writing Complexity Score",
                "description": "A measure of the linguistic complexity of the judge's written opinions.",
                "data_source": "Full text of opinions from CourtListener.",
                "calculation": "Over up to 100 opinions with full text, the sum of three components: average sentence length in words / 10 (max 3), vocabulary diversity (unique words / total words) x 10 (max 3), and average opinion length in words / 2,500 (max 4). Range 0-10.",
                "limitations": "A heuristic with no external benchmark: the component weights and caps are fixed choices, not calibrated against other judges. Legal writing is inherently complex. Complexity doesn't indicate quality. Some simple opinions address simple issues; some complex opinions address complex issues appropriately.",
                "interpretation": "Higher scores mean longer sentences, more varied vocabulary and longer opinions. Use it to compare judges with each other, not as an absolute rating.",
            },
            "opinion_length_trend": {
                "name": "Opinion Length Trend",
                "description": "How the judge's average opinion length has changed over time.",
                "data_source": "Word counts from CourtListener opinion text, grouped by year.",
                "calculation": "Average word count per year. A least-squares slope across years gives the direction: increasing above +50 words per year, decreasing below -50, otherwise stable. The ten most recent years are shown.",
                "limitations": "Opinion length depends on case complexity. Changes may reflect changing caseload mix, not writing style changes.",
                "interpretation": "Increasing length may indicate more thorough analysis or complex caseload. Decreasing length may indicate efficiency or simpler cases.",
            },
            "political_alignment_indicator": {
                "name": "Appointing Authority",
                "description": "Information about who appointed this judge, which may suggest judicial philosophy.",
                "data_source": "CourtListener biographical data and Federal Judicial Center records.",
                "calculation": "Not calculated - factual record of appointing president/governor and political party.",
                "limitations": "IMPORTANT: Appointing authority does NOT reliably predict rulings. Many judges rule independently of perceived political expectations. This is background information only.",
                "interpretation": "Use for context only. Do not assume ruling patterns based on appointment. Focus on the judge's actual record and written opinions.",
            },
            "bench_experience": {
                "name": "Judicial Experience",
                "description": "Total years on the bench and progression through different court levels.",
                "data_source": "CourtListener position history.",
                "calculation": "Sum of years in each judicial position, with breakdown by court level.",
                "limitations": "Years of experience don't directly correlate with quality. Prior legal experience (as attorney) not fully captured.",
                "interpretation": "More experienced judges may have established patterns. Newer judges may be less predictable but potentially more open to novel arguments.",
            },
            "data_completeness": {
                "name": "Data Completeness Score",
                "description": "How complete our data is for this judge, affecting reliability of other metrics.",
                "data_source": "Internal assessment of available data.",
                "calculation": "Percentage of seven checks that pass, each counted equally: biographical info, birth date, education, positions, opinions, dockets, and opinion full text.",
                "limitations": "N/A",
                "interpretation": "Scores below 70% suggest treating other metrics with additional caution. Historical judges typically have less complete data.",
            },
        }

    async def compute_advanced_metrics(
        self, judge_id: int, force_recompute: bool = False
    ) -> dict[str, Any]:
        """
        Compute advanced analytics metrics for a judge.
        Results are cached inside the judge_data JSON.

        Returns dict with metrics and their methodology explanations.
        """
        cache_row = await self._get_cache(judge_id)
        if not cache_row:
            return {
                "methodology": self.get_metrics_methodology(),
                "computed_at": None,
                "metrics": {},
            }

        judge_data = self._parse_judge_data(cache_row)
        opinions_data = self._parse_opinions_data(cache_row)

        # Check for previously computed metrics (cached for 24h)
        if not force_recompute:
            cached_metrics = judge_data.get("_computed_metrics")
            if cached_metrics:
                computed_at_str = cached_metrics.get("computed_at")
                if computed_at_str:
                    try:
                        computed_at = datetime.fromisoformat(computed_at_str)
                        if datetime.now(UTC) - computed_at.replace(tzinfo=UTC) < timedelta(
                            hours=24
                        ):
                            return cached_metrics
                    except (ValueError, TypeError):
                        pass

        opinions = opinions_data.get("opinions", [])
        dockets = opinions_data.get("dockets", [])
        positions = judge_data.get("positions", [])
        education = judge_data.get("education", [])

        metrics = {
            "methodology": self.get_metrics_methodology(),
            "computed_at": datetime.now(UTC).isoformat(),
            "metrics": {},
        }

        # ===== DISSENT & CONCURRENCE RATES =====
        opinion_types: dict[str, int] = {}
        for op in opinions:
            ot = (op.get("opinion_type") or "").lower().strip()
            if ot:
                opinion_types[ot] = opinion_types.get(ot, 0) + 1

        total_typed = sum(opinion_types.values())
        dissent_count = sum(v for k, v in opinion_types.items() if "dissent" in k)
        concur_count = sum(v for k, v in opinion_types.items() if "concur" in k)

        metrics["metrics"]["dissent_rate"] = {
            "value": round((dissent_count / total_typed * 100), 2) if total_typed > 0 else None,
            "dissent_count": dissent_count,
            "total_opinions_analyzed": total_typed,
            "data_quality": "good"
            if total_typed >= 50
            else "limited"
            if total_typed >= 10
            else "insufficient",
        }

        metrics["metrics"]["concurrence_rate"] = {
            "value": round((concur_count / total_typed * 100), 2) if total_typed > 0 else None,
            "concurrence_count": concur_count,
            "total_opinions_analyzed": total_typed,
            "data_quality": "good"
            if total_typed >= 50
            else "limited"
            if total_typed >= 10
            else "insufficient",
        }

        # ===== CITATION IMPACT SCORE =====
        total_opinions = len(opinions)
        total_citations = sum(op.get("citation_count", 0) for op in opinions)
        avg_citations = total_citations / total_opinions if total_opinions > 0 else 0
        max_citations = max((op.get("citation_count", 0) for op in opinions), default=0)
        first_opinion_date = min(
            (op.get("date_filed") for op in opinions if op.get("date_filed")),
            default=None,
        )

        years_on_bench = 1
        if first_opinion_date:
            first_year_match = re.search(r"(1[7-9]\d{2}|20\d{2})", str(first_opinion_date))
            if first_year_match:
                first_year = int(first_year_match.group(1))
                years_on_bench = max(1, datetime.now().year - first_year)

        raw_impact = avg_citations * math.log(years_on_bench + 1)
        normalized_impact = min(5.0, raw_impact / 35) if raw_impact else 0

        metrics["metrics"]["citation_impact_score"] = {
            "value": round(normalized_impact, 2),
            "total_citations": total_citations,
            "avg_citations_per_opinion": round(avg_citations, 2),
            "most_cited_opinion_citations": max_citations,
            "years_on_bench": years_on_bench,
            "data_quality": "good" if total_opinions >= 50 else "limited",
        }

        # ===== CASE DISPOSITION TIME =====
        durations = []
        for d in dockets:
            try:
                filed_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(d.get("date_filed", "")))
                term_match = re.search(
                    r"(\d{4})-(\d{2})-(\d{2})", str(d.get("date_terminated", ""))
                )
                if filed_match and term_match:
                    filed = date(
                        int(filed_match.group(1)),
                        int(filed_match.group(2)),
                        int(filed_match.group(3)),
                    )
                    terminated = date(
                        int(term_match.group(1)),
                        int(term_match.group(2)),
                        int(term_match.group(3)),
                    )
                    duration = (terminated - filed).days
                    if 0 < duration < 3650:
                        durations.append(duration)
            except (ValueError, TypeError, AttributeError):
                pass

        avg_duration = sum(durations) / len(durations) if durations else None
        metrics["metrics"]["case_disposition_time"] = {
            "value_days": round(avg_duration, 1) if avg_duration else None,
            "value_months": round(avg_duration / 30.44, 1) if avg_duration else None,
            "cases_analyzed": len(durations),
            "median_days": sorted(durations)[len(durations) // 2] if durations else None,
            "fastest_case_days": min(durations) if durations else None,
            "slowest_case_days": max(durations) if durations else None,
            "data_quality": "good"
            if len(durations) >= 30
            else "limited"
            if len(durations) >= 10
            else "insufficient",
        }

        # ===== CASE TYPE EXPERTISE =====
        suit_counts: dict[str, int] = {}
        for d in dockets:
            nos = d.get("nature_of_suit")
            if nos:
                suit_counts[nos] = suit_counts.get(nos, 0) + 1

        case_types = sorted(
            [{"type": k, "count": v} for k, v in suit_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
        total_cases = sum(ct["count"] for ct in case_types)
        for ct in case_types:
            ct["percentage"] = round(ct["count"] / total_cases * 100, 1) if total_cases > 0 else 0

        metrics["metrics"]["case_type_expertise"] = {
            "distribution": case_types[:15],
            "total_cases_analyzed": total_cases,
            "primary_expertise": case_types[0]["type"] if case_types else None,
            "expertise_concentration": case_types[0]["percentage"] if case_types else 0,
            "data_quality": "good"
            if total_cases >= 50
            else "limited"
            if total_cases >= 10
            else "insufficient",
        }

        # ===== WRITING COMPLEXITY =====
        word_counts = []
        sentence_lengths = []
        vocab_diversities = []

        for op in opinions[:100]:
            text = op.get("full_text", "")
            if not text:
                continue
            word_count = op.get("word_count") or len(text.split())
            word_counts.append(word_count)

            sentences = re.split(r"[.!?]+", text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
            if sentences:
                avg_sent_len = sum(len(s.split()) for s in sentences) / len(sentences)
                sentence_lengths.append(avg_sent_len)

            words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
            if len(words) > 100:
                diversity = len(set(words)) / len(words)
                vocab_diversities.append(diversity)

        complexity_score = None
        if sentence_lengths and vocab_diversities:
            avg_sent_len = sum(sentence_lengths) / len(sentence_lengths)
            avg_diversity = sum(vocab_diversities) / len(vocab_diversities)
            avg_length = sum(word_counts) / len(word_counts) if word_counts else 0

            sent_component = min(3, avg_sent_len / 10)
            diversity_component = min(3, avg_diversity * 10)
            length_component = min(4, avg_length / 2500)
            complexity_score = round(sent_component + diversity_component + length_component, 1)

        metrics["metrics"]["writing_complexity"] = {
            "score": complexity_score,
            "avg_opinion_length_words": round(sum(word_counts) / len(word_counts))
            if word_counts
            else None,
            "avg_sentence_length_words": round(sum(sentence_lengths) / len(sentence_lengths), 1)
            if sentence_lengths
            else None,
            "vocabulary_diversity": round(sum(vocab_diversities) / len(vocab_diversities), 3)
            if vocab_diversities
            else None,
            "opinions_analyzed": len(word_counts),
            "data_quality": "good"
            if len(word_counts) >= 20
            else "limited"
            if len(word_counts) >= 5
            else "insufficient",
        }

        # ===== OPINION LENGTH TREND =====
        yearly_lengths: dict[str, list[int]] = {}
        for op in opinions:
            wc = op.get("word_count", 0)
            df = op.get("date_filed")
            if df and wc and wc > 0:
                year_match = re.search(r"(1[7-9]\d{2}|20\d{2})", str(df))
                if year_match:
                    year = year_match.group(1)
                    yearly_lengths.setdefault(year, []).append(wc)

        trend_data = []
        for year in sorted(yearly_lengths.keys()):
            lengths = yearly_lengths[year]
            trend_data.append(
                {
                    "year": year,
                    "avg_length": round(sum(lengths) / len(lengths)),
                    "opinion_count": len(lengths),
                }
            )

        trend_direction = "stable"
        if len(trend_data) >= 3:
            years_list = [int(t["year"]) for t in trend_data]
            lengths_list = [t["avg_length"] for t in trend_data]
            n = len(years_list)
            sum_x = sum(years_list)
            sum_y = sum(lengths_list)
            sum_xy = sum(x * y for x, y in zip(years_list, lengths_list, strict=False))
            sum_x2 = sum(x * x for x in years_list)

            slope = (
                (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                if (n * sum_x2 - sum_x * sum_x) != 0
                else 0
            )

            if slope > 50:
                trend_direction = "increasing"
            elif slope < -50:
                trend_direction = "decreasing"

        metrics["metrics"]["opinion_length_trend"] = {
            "trend_direction": trend_direction,
            "yearly_data": trend_data[-10:],
            "data_quality": "good"
            if len(trend_data) >= 5
            else "limited"
            if len(trend_data) >= 2
            else "insufficient",
        }

        # ===== BENCH EXPERIENCE =====
        positions_list = []
        total_years = 0
        for pos in positions:
            p = {
                "position": pos.get("position_type"),
                "court": pos.get("court_name"),
                "start": pos.get("date_start"),
                "end": pos.get("date_termination"),
            }
            try:
                start_match = (
                    re.search(r"(\d{4})", str(pos.get("date_start")))
                    if pos.get("date_start")
                    else None
                )
                end_match = (
                    re.search(r"(\d{4})", str(pos.get("date_termination")))
                    if pos.get("date_termination")
                    else None
                )
                start_year = int(start_match.group(1)) if start_match else None
                end_year = int(end_match.group(1)) if end_match else datetime.now().year
                if start_year:
                    yrs = end_year - start_year
                    p["years"] = yrs
                    total_years += yrs
            except (ValueError, TypeError, AttributeError):
                pass
            positions_list.append(p)

        metrics["metrics"]["bench_experience"] = {
            "total_years": total_years,
            "positions": positions_list,
            "current_position": positions_list[-1] if positions_list else None,
            "data_quality": "good" if positions_list else "insufficient",
        }

        # ===== DATA COMPLETENESS SCORE =====
        completeness_checks = {
            "biographical_info": bool(judge_data.get("name") or judge_data.get("name_first")),
            "birth_date": bool(judge_data.get("date_of_birth")),
            "education": bool(education),
            "positions": bool(positions),
            "opinions": total_opinions > 0,
            "dockets": total_cases > 0,
            "opinion_full_text": bool(word_counts),
        }

        completeness_score = sum(completeness_checks.values()) / len(completeness_checks) * 100

        metrics["metrics"]["data_completeness"] = {
            "score": round(completeness_score, 1),
            "checks": completeness_checks,
            "recommendation": "High confidence in metrics"
            if completeness_score >= 70
            else "Moderate confidence - some data missing"
            if completeness_score >= 40
            else "Low confidence - significant data gaps",
        }

        # ===== CACHE THE RESULTS inside judge_data =====
        judge_data["_computed_metrics"] = metrics
        await self._set_cache(judge_id, judge_data, opinions_data)

        return metrics
