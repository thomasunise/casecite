"""Query/read-back mixin for JudgeIntelService."""

import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


class QueriesMixin:
    """Read-back methods that query the judge cache."""

    async def get_judge_profile(self, judge_id: int) -> dict[str, Any] | None:
        """Get complete judge profile from the database cache."""
        cache_row = await self._get_cache(judge_id)
        if not cache_row:
            return None

        judge = self._parse_judge_data(cache_row)
        opinions_data = self._parse_opinions_data(cache_row)

        opinions = opinions_data.get("opinions", [])
        dockets = opinions_data.get("dockets", [])

        # Opinion stats
        total_opinions = len(opinions)
        total_citations = sum(op.get("citation_count", 0) for op in opinions)
        avg_citations = total_citations / total_opinions if total_opinions > 0 else 0
        dates_filed = [op.get("date_filed") for op in opinions if op.get("date_filed")]
        total_words = sum(op.get("word_count", 0) for op in opinions)

        judge["opinion_stats"] = {
            "total_opinions": total_opinions,
            "total_citations": total_citations,
            "avg_citations": round(avg_citations, 2),
            "first_opinion": min(dates_filed) if dates_filed else None,
            "last_opinion": max(dates_filed) if dates_filed else None,
            "total_words": total_words,
        }

        # Opinions by court
        court_counts: dict[str, int] = {}
        for op in opinions:
            c = op.get("court", "")
            if c:
                court_counts[c] = court_counts.get(c, 0) + 1
        judge["opinions_by_court"] = sorted(
            [{"court": k, "count": v} for k, v in court_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

        # Opinions by year
        year_counts: dict[str, int] = {}
        for op in opinions:
            date_str = op.get("date_filed")
            if date_str:
                year_match = re.search(r"\b(1[7-9]\d{2}|20\d{2})\b", str(date_str))
                if year_match:
                    year = year_match.group(1)
                    year_counts[year] = year_counts.get(year, 0) + 1
        judge["opinions_by_year"] = [
            {"year": year, "count": count} for year, count in sorted(year_counts.items())
        ]

        # Most cited opinions
        sorted_by_cite = sorted(opinions, key=lambda x: x.get("citation_count", 0), reverse=True)
        judge["most_cited_opinions"] = [
            {
                "id": op.get("id"),
                "case_name": op.get("case_name"),
                "citation": op.get("citation"),
                "citation_count": op.get("citation_count", 0),
                "date_filed": op.get("date_filed"),
                "court": op.get("court"),
                "url": op.get("url"),
            }
            for op in sorted_by_cite[:20]
        ]

        # Docket stats
        if not dockets and judge.get("name") and self.api_token:
            # Auto-fetch dockets if none exist (needs a token; skip silently without one)
            try:
                new_dockets = await self._pull_assigned_dockets(
                    judge_id=judge_id,
                    judge_name=judge["name"],
                    progress_callback=lambda x: None,
                    max_dockets=50,
                )
                if new_dockets:
                    opinions_data["dockets"] = new_dockets
                    dockets = new_dockets
                    await self._set_cache(judge_id, judge, opinions_data)
            except (
                ValueError,
                KeyError,
                ConnectionError,
                TimeoutError,
                OSError,
                RuntimeError,
            ) as e:
                logger.error(f"Auto-fetch dockets failed for judge {judge_id}: {e}")

        docket_dates = [d.get("date_filed") for d in dockets if d.get("date_filed")]
        judge["docket_stats"] = {
            "total_dockets": len(dockets),
            "first_docket": min(docket_dates) if docket_dates else None,
            "last_docket": max(docket_dates) if docket_dates else None,
        }

        # Recent assigned cases
        sorted_dockets = sorted(dockets, key=lambda x: x.get("date_filed") or "", reverse=True)
        judge["recent_dockets"] = [
            {
                "id": d.get("id"),
                "case_name": d.get("case_name"),
                "court": d.get("court"),
                "date_filed": d.get("date_filed"),
                "docket_number": d.get("docket_number"),
                "nature_of_suit": d.get("nature_of_suit"),
                "url": d.get("url"),
            }
            for d in sorted_dockets[:20]
        ]

        # Dockets by nature of suit
        suit_counts: dict[str, int] = {}
        for d in dockets:
            nos = d.get("nature_of_suit")
            if nos:
                suit_counts[nos] = suit_counts.get(nos, 0) + 1
        judge["dockets_by_type"] = sorted(
            [{"nature_of_suit": k, "count": v} for k, v in suit_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # Remove large internal fields from response
        judge.pop("wikipedia_raw", None)
        judge.pop("_computed_metrics", None)

        return judge

    async def get_judge_metrics_with_explanations(
        self, judge_id: int, force_recompute: bool = False
    ) -> dict[str, Any]:
        """
        Get just the advanced metrics with full methodology explanations.
        Useful for dedicated metrics display or API endpoint.

        Returns:
            {
                "judge_id": int,
                "judge_name": str,
                "metrics": {metric_name: {value, data_quality, ...}},
                "methodology": {metric_name: {description, calculation, limitations, interpretation}},
                "computed_at": timestamp,
                "summary": {
                    "strengths": [...],
                    "cautions": [...],
                    "data_quality_overall": "good"|"limited"|"insufficient"
                }
            }
        """
        cache_row = await self._get_cache(judge_id)
        judge_name = "Unknown"
        if cache_row:
            jd = self._parse_judge_data(cache_row)
            judge_name = jd.get("name", "Unknown")

        # Compute metrics
        metrics_data = await self.compute_advanced_metrics(judge_id, force_recompute)

        # Generate summary insights
        metrics = metrics_data.get("metrics", {})
        strengths = []
        cautions = []

        # Analyze citation impact
        citation_impact = metrics.get("citation_impact_score", {})
        if citation_impact.get("value") and citation_impact.get("value") > 2.0:
            strengths.append(
                f"High citation impact ({citation_impact['value']}) - opinions are frequently cited by other courts"
            )
        elif citation_impact.get("value") and citation_impact.get("value") < 0.5:
            cautions.append(
                "Lower citation impact may indicate newer judge or specialized practice area"
            )

        # Analyze dissent rate
        dissent = metrics.get("dissent_rate", {})
        if dissent.get("value") and dissent.get("value") > 20:
            cautions.append(
                f"Higher than average dissent rate ({dissent['value']}%) - may indicate independent judicial philosophy"
            )
        elif dissent.get("data_quality") == "insufficient":
            cautions.append(
                "Insufficient data for dissent rate analysis - likely a trial court judge or limited appellate data"
            )

        # Analyze case duration
        duration = metrics.get("case_disposition_time", {})
        if duration.get("value_months"):
            if duration["value_months"] > 24:
                cautions.append(
                    f"Longer average case duration ({duration['value_months']} months) - may handle complex cases or have heavy caseload"
                )
            elif duration["value_months"] < 6:
                strengths.append(
                    f"Efficient case resolution (average {duration['value_months']} months)"
                )

        # Analyze data completeness
        completeness = metrics.get("data_completeness", {})
        overall_quality = "good"
        if completeness.get("score", 0) < 40:
            overall_quality = "insufficient"
            cautions.append("Limited data available - interpret all metrics with caution")
        elif completeness.get("score", 0) < 70:
            overall_quality = "limited"
            cautions.append("Some data gaps exist - some metrics may be less reliable")

        # Analyze expertise
        expertise = metrics.get("case_type_expertise", {})
        if expertise.get("primary_expertise"):
            strengths.append(f"Most experience with: {expertise['primary_expertise']}")

        return {
            "judge_id": judge_id,
            "judge_name": judge_name,
            "metrics": metrics,
            "methodology": metrics_data.get("methodology", {}),
            "computed_at": metrics_data.get("computed_at"),
            "summary": {
                "strengths": strengths,
                "cautions": cautions,
                "data_quality_overall": overall_quality,
                "recommendation": completeness.get(
                    "recommendation", "Review individual metric quality ratings"
                ),
            },
        }

    async def query_opinions(
        self,
        judge_id: int,
        query: str | None = None,
        court: str | None = None,
        year_start: int | None = None,
        year_end: int | None = None,
        min_citations: int | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "date",
    ) -> dict[str, Any]:
        """
        Query judge's opinions with filters.

        order: "date" (newest first) or "citations" (most cited first).
        """
        cache_row = await self._get_cache(judge_id)
        if not cache_row:
            return {"total": 0, "limit": limit, "offset": offset, "opinions": []}

        opinions_data = self._parse_opinions_data(cache_row)
        opinions = opinions_data.get("opinions", [])

        # Apply filters
        filtered = opinions

        if query:
            q_lower = query.lower()
            filtered = [
                op
                for op in filtered
                if q_lower in (op.get("case_name") or "").lower()
                or q_lower in (op.get("full_text") or "").lower()
            ]

        if court:
            c_lower = court.lower()
            filtered = [op for op in filtered if c_lower in (op.get("court") or "").lower()]

        if year_start:
            filtered = [
                op
                for op in filtered
                if op.get("date_filed") and str(op["date_filed"])[:4] >= str(year_start)
            ]

        if year_end:
            filtered = [
                op
                for op in filtered
                if op.get("date_filed") and str(op["date_filed"])[:4] <= str(year_end)
            ]

        if min_citations:
            filtered = [op for op in filtered if (op.get("citation_count") or 0) >= min_citations]

        if order == "citations":
            filtered.sort(key=lambda x: x.get("citation_count") or 0, reverse=True)
        else:
            filtered.sort(key=lambda x: x.get("date_filed") or "", reverse=True)

        total = len(filtered)
        page = filtered[offset : offset + limit]

        # Return with snippet instead of full text
        result_opinions = []
        for op in page:
            result_op = {
                "id": op.get("id"),
                "case_name": op.get("case_name"),
                "case_name_short": op.get("case_name_short"),
                "court": op.get("court"),
                "date_filed": op.get("date_filed"),
                "docket_number": op.get("docket_number"),
                "citation": op.get("citation"),
                "citation_count": op.get("citation_count"),
                "url": op.get("url"),
                "snippet": (op.get("full_text") or op.get("snippet") or "")[:500],
            }
            result_opinions.append(result_op)

        return {"total": total, "limit": limit, "offset": offset, "opinions": result_opinions}

    async def get_opinion_full_text(self, judge_id: int, opinion_id: int) -> dict[str, Any] | None:
        """Full text of one of this judge's cached opinions.

        The profile build fetches text only for the most-cited opinions; for
        the rest, fetch it from CourtListener on first open and keep it in the
        cache so the next open is instant.
        """
        cache_row = await self._get_cache(judge_id)
        if not cache_row:
            return None
        judge_data = self._parse_judge_data(cache_row)
        opinions_data = self._parse_opinions_data(cache_row)
        opinions = opinions_data.get("opinions", [])
        op = next((o for o in opinions if str(o.get("id")) == str(opinion_id)), None)
        if op is None:
            return None

        if not (op.get("full_text") or "").strip() and self.api_token:
            # Cached opinions are keyed by CLUSTER id (what search returns); the
            # text lives on the cluster's sub-opinions.
            try:
                from app.services.courtlistener_gate import cl_client

                async with cl_client(timeout=60.0) as client:
                    text, parts = await self._fetch_cluster_text(client, int(opinion_id))
                if text:
                    op["full_text"] = text[:100000]
                    op["word_count"] = len(text.split())
                    op["opinion_parts"] = parts
                    op.pop("text_unavailable", None)
                else:
                    op["text_unavailable"] = True
                await self._set_cache(judge_id, judge_data, opinions_data)
            except (
                ValueError,
                KeyError,
                ConnectionError,
                TimeoutError,
                OSError,
                RuntimeError,
            ) as e:
                logger.warning(f"Live full-text fetch failed for opinion {opinion_id}: {e}")
        return op

    async def get_statistics(self, judge_id: int) -> dict[str, Any]:
        """Get comprehensive statistics for a judge."""
        cache_row = await self._get_cache(judge_id)
        if not cache_row:
            return {}

        opinions_data = self._parse_opinions_data(cache_row)
        opinions = opinions_data.get("opinions", [])

        stats: dict[str, Any] = {}

        # Basic counts
        total_opinions = len(opinions)
        total_citations = sum(op.get("citation_count", 0) for op in opinions)
        avg_citations = total_citations / total_opinions if total_opinions > 0 else 0
        max_citations_val = max((op.get("citation_count", 0) for op in opinions), default=0)
        word_counts = [op.get("word_count", 0) for op in opinions]
        avg_opinion_length = sum(word_counts) / len(word_counts) if word_counts else 0
        total_words = sum(word_counts)

        stats["overview"] = {
            "total_opinions": total_opinions,
            "total_citations": total_citations,
            "avg_citations_per_opinion": round(avg_citations, 2),
            "max_citations": max_citations_val,
            "avg_opinion_length": round(avg_opinion_length, 1),
            "total_words_written": total_words,
        }

        # By year
        year_data: dict[str, dict] = {}
        for op in opinions:
            date_str = op.get("date_filed")
            if date_str:
                year_match = re.search(r"\b(1[7-9]\d{2}|20\d{2})\b", str(date_str))
                if year_match:
                    year = year_match.group(1)
                    if year not in year_data:
                        year_data[year] = {"opinions": 0, "citations": 0, "word_counts": []}
                    year_data[year]["opinions"] += 1
                    year_data[year]["citations"] += op.get("citation_count", 0)
                    wc = op.get("word_count", 0)
                    if wc:
                        year_data[year]["word_counts"].append(wc)

        stats["by_year"] = [
            {
                "year": year,
                "opinions": data["opinions"],
                "citations": data["citations"],
                "avg_length": sum(data["word_counts"]) / len(data["word_counts"])
                if data["word_counts"]
                else 0,
            }
            for year, data in sorted(year_data.items())
        ]

        # By court
        court_data: dict[str, dict] = {}
        for op in opinions:
            c = op.get("court", "")
            if c:
                if c not in court_data:
                    court_data[c] = {"opinions": 0, "citations": 0}
                court_data[c]["opinions"] += 1
                court_data[c]["citations"] += op.get("citation_count", 0)
        stats["by_court"] = sorted(
            [
                {
                    "court": k,
                    "opinions": v["opinions"],
                    "citations": v["citations"],
                    "avg_citations": round(v["citations"] / v["opinions"], 2)
                    if v["opinions"] > 0
                    else 0,
                }
                for k, v in court_data.items()
            ],
            key=lambda x: x["opinions"],
            reverse=True,
        )

        # By day of week
        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        day_counts: dict[str, int] = {}
        for op in opinions:
            date_str = op.get("date_filed")
            if date_str:
                try:
                    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(date_str))
                    if match:
                        d = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                        day_name = day_names[d.weekday()]
                        day_counts[day_name] = day_counts.get(day_name, 0) + 1
                except (ValueError, TypeError):
                    pass
        stats["by_day_of_week"] = [
            {"day_of_week": day, "opinions": day_counts.get(day, 0)} for day in day_names
        ]

        # By month
        month_counts: dict[str, int] = {}
        for op in opinions:
            date_str = str(op.get("date_filed", ""))
            month_match = re.search(r"\d{4}-(\d{2})-\d{2}", date_str)
            if month_match:
                month = month_match.group(1)
                month_counts[month] = month_counts.get(month, 0) + 1
        stats["by_month"] = [
            {"month": month, "opinions": count} for month, count in sorted(month_counts.items())
        ]

        # Citation distribution
        ranges = [
            ("0", lambda c: c == 0),
            ("1-5", lambda c: 1 <= c <= 5),
            ("6-20", lambda c: 6 <= c <= 20),
            ("21-50", lambda c: 21 <= c <= 50),
            ("51-100", lambda c: 51 <= c <= 100),
            ("100+", lambda c: c > 100),
        ]
        cite_dist: dict[str, int] = {}
        for op in opinions:
            c = op.get("citation_count", 0)
            for label, check in ranges:
                if check(c):
                    cite_dist[label] = cite_dist.get(label, 0) + 1
                    break
        stats["citation_distribution"] = [
            {"citation_range": label, "count": cite_dist.get(label, 0)} for label, _ in ranges
        ]

        return stats

    async def is_judge_cached(self, judge_id: int) -> bool:
        """Check if we already have data for this judge."""
        row = await self._get_cache(judge_id)
        return row is not None

    async def delete_judge_cache(self, judge_id: int):
        """Delete all cached data for a judge."""
        await self._delete_cache(judge_id)
