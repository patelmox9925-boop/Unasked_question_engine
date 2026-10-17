"""Domain probes: what experienced reviewers ask about each kind of project.

They steer the analyst toward questions teams commonly forget. They are prompts to think with, not
findings: the analyst is told to raise one only if the material makes it relevant, and every finding
must still be grounded in the project's own text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..extraction.models import Chunk


@dataclass(frozen=True)
class Domain:
    key: str
    name: str
    pattern: re.Pattern[str]
    probes: tuple[str, ...]


def _rx(words: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{words})", re.IGNORECASE)


DOMAINS: tuple[Domain, ...] = (
    Domain("software", "Software or web product", _rx(
        r"app\b|apps\b|website|web app|api\b|backend|frontend|database|server|cloud|deploy|release|login|"
        r"authenticat|mobile|saas|platform|integration|codebase|sprint|feature"),
        (
            "Who can do what (roles, admin access, how accounts are created and removed)?",
            "What happens when it breaks: monitoring, on-call, rollback, backups and restore tests?",
            "Which third-party services does it depend on, and what are their limits, prices and failure modes?",
            "Where does existing data come from, and how is it migrated and checked?",
            "What does it cost to run at 10x the expected usage?",
            "How are personal or payment data stored, retained and deleted?",
            "What is the definition of done, and who accepts it?",
            "Which parts are hardest or least understood, and have they been tried (spikes, prototypes)?",
        )),
    Domain("data", "Dataset or analytics", _rx(
        r"dataset|csv|column|rows?\b|records?\b|survey|metric|kpi|dashboard|analytics|model\b|training|"
        r"sample size|forecast|report"),
        (
            "Are there empty, duplicated or impossible values, and what do they do to the totals?",
            "Does the data cover the whole population, period and region the conclusions are about?",
            "How is each metric defined, and does everyone calculate it the same way?",
            "Who owns the data, how fresh is it, and what happens when the source changes?",
            "Are any conclusions drawn from too few records or from outliers?",
            "Can the figures in the written material be reproduced from the data supplied?",
        )),
    Domain("business", "Product launch or business plan", _rx(
        r"launch|customer|market|revenue|pricing|subscri|sales|growth|competitor|startup|funding|"
        r"investor|churn|marketing|brand|retail|order|delivery"),
        (
            "What evidence exists that customers want this and will pay this price?",
            "What are the unit economics at small and at large scale?",
            "What must be true for the growth target to be reached, and who tests those assumptions?",
            "Which promises to customers (speed, price, quality) does operations actually support?",
            "What happens if the launch date or the key supplier slips?",
            "What do customers do when something goes wrong, and who answers them?",
        )),
    Domain("operations", "Process, team or workflow", _rx(
        r"workflow|process|team\b|staff|hire|hiring|train|handover|schedule|shift|policy|procedure|"
        r"approval|vendor|supplier|warehouse|logistics|support|onboarding"),
        (
            "Who owns each step, and what happens when that person is away?",
            "Where do handoffs happen, and what is lost at each one?",
            "Which steps depend on one person, one spreadsheet or one manual action?",
            "How will the team know it is working (measures) and that it has stopped working (alerts)?",
            "What are the capacity limits (people, hours, volume) before quality drops?",
        )),
    Domain("compliance", "Regulated or sensitive data", _rx(
        r"personal data|health|medical|allerg|patient|children|minor|payment|card|bank|finance|legal|"
        r"contract|gdpr|hipaa|pci|compliance|consent|privacy|biometric"),
        (
            "Which rules might apply to this data or activity (to verify with a specialist, not assume)?",
            "What consent, retention and deletion arrangements exist?",
            "Who can see the sensitive data, and is access logged?",
            "What is the harm if the data is wrong, lost or leaked, and who is affected?",
        )),
)


def detect_domains(chunks: list[Chunk], max_domains: int = 3) -> list[Domain]:
    text = "\n".join(c.text for c in chunks)
    has_dataset = any(c.kind in ("dataset_profile", "dataset_rows") for c in chunks)
    scored: list[tuple[int, Domain]] = []
    for domain in DOMAINS:
        hits = len(domain.pattern.findall(text))
        if domain.key == "data" and has_dataset:
            hits += 5
        if hits >= 2:
            scored.append((hits, domain))
    scored.sort(key=lambda t: -t[0])
    return [d for _, d in scored[:max_domains]]


def checklist_text(domains: list[Domain]) -> str:
    if not domains:
        return ""
    blocks = [f"{d.name}:\n" + "\n".join(f"  - {p}" for p in d.probes) for d in domains]
    return (
        "PROBE AREAS (questions experienced reviewers ask for this kind of project; raise one only if "
        "this material makes it relevant, and ground it in the material's own words):\n" + "\n".join(blocks)
    )
