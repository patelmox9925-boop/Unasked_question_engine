"""Adaptive perspective selection.

Perspectives are chosen from keyword evidence in the provided material, so a
CSV-only upload is not interrogated about UX and a small internal tool is not
interrogated about multi-region scaling. Technical feasibility and missing
requirements/assumptions always apply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..extraction.models import Chunk
from ..schemas import PerspectiveInfo


@dataclass(frozen=True)
class Perspective:
    key: str
    name: str
    focus: str
    pattern: re.Pattern[str] | None = None  # None => always relevant


def _rx(words: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{words})", re.IGNORECASE)


CATALOG: tuple[Perspective, ...] = (
    Perspective("technical", "Technical feasibility",
                "Is the approach realistic with the stated skills, tools, timeline and architecture? "
                "What technical unknowns or hard problems are not addressed?"),
    Perspective("requirements", "Missing requirements and assumptions",
                "What is assumed but never stated or validated? What requirements, owners, success "
                "criteria or decisions are absent? Where do statements contradict each other?"),
    Perspective("cost", "Cost and resource constraints",
                "Are budget, staffing, licences, hosting or running costs realistic and complete? "
                "What hidden or recurring costs are missing?",
                _rx(r"budget|cost|price|pricing|fund|usd|eur|inr|salary|hire|hiring|invoice|licen[cs]e|"
                    r"headcount|spend|\$\s?\d")),
    Perspective("security", "Security and privacy",
                "How are identity, access, secrets, personal data, retention and compliance handled? "
                "(Flag items to verify with a specialist; do not assert legal conclusions.)",
                _rx(r"auth|password|login|token|encrypt|pii|personal data|gdpr|hipaa|privacy|complian|"
                    r"secret|permission|credential|access control|audit")),
    Perspective("scalability", "Scalability and reliability",
                "What happens under growth, peaks, failures or outages? Are availability, latency and "
                "recovery expectations defined?",
                _rx(r"scal|traffic|load|concurren|throughput|latency|uptime|availab|peak|growth|"
                    r"million|thousand users|capacity|failover|outage")),
    Perspective("dependencies", "Dependencies and integration",
                "Which vendors, APIs, teams, data sources or approvals does this rely on? What if one "
                "is late, changes, or is unavailable?",
                _rx(r"api|vendor|third[- ]party|integrat|depend|supplier|partner|migrat|webhook|"
                    r"sso|legacy|external|contract")),
    Perspective("ux", "User experience",
                "Who are the users, what do they need, and what could make adoption or day-to-day use "
                "fail (accessibility, onboarding, error states, edge cases)?",
                _rx(r"interface|ux\b|ui\b|onboard|accessib|usab|mobile app|screen|front-?end|"
                    r"customer experience|wireframe|persona|adoption")),
    Perspective("operations", "Operational risks",
                "Who runs, monitors, supports and maintains this after launch? What are the rollout, "
                "backup, incident and training gaps?",
                _rx(r"deploy|monitor|support|on-?call|maintenance|incident|backup|release|rollout|"
                    r"staffing|training|runbook|sla\b|process|handover")),
    Perspective("data_quality", "Data quality and consistency",
                "Are datasets complete, consistent and plausible? Look at empty cells, outliers, "
                "duplicates, units and conflicts between tables and the written plan."),
)


def select_perspectives(chunks: list[Chunk]) -> list[tuple[Perspective, PerspectiveInfo]]:
    text = "\n".join(c.text for c in chunks)
    has_dataset = any(c.kind in ("dataset_profile", "dataset_rows") for c in chunks)
    selected: list[tuple[Perspective, PerspectiveInfo]] = []
    for p in CATALOG:
        if p.key == "data_quality":
            if has_dataset:
                selected.append((p, PerspectiveInfo(key=p.key, name=p.name,
                                                    reason="A dataset (CSV) was provided.")))
            continue
        if p.pattern is None:
            selected.append((p, PerspectiveInfo(key=p.key, name=p.name,
                                                reason="Applies to every project.")))
            continue
        terms: list[str] = []
        for match in p.pattern.finditer(text):
            term = match.group(0).strip().lower()
            if term not in terms:
                terms.append(term)
            if len(terms) == 4:
                break
        if terms:
            selected.append((p, PerspectiveInfo(
                key=p.key, name=p.name, reason="The material mentions: " + ", ".join(terms) + ".")))
    return selected
