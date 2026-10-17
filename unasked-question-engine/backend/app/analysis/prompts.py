"""Prompt construction for roles A (analysis), B (critique) and C (synthesis).

All user material is rendered through ``format_untrusted_context`` and the system
prompts carry ``UNTRUSTED_DATA_RULES``. Prompts contain no secrets.
"""

from __future__ import annotations

import json
from typing import Any

from ..extraction.untrusted import UNTRUSTED_DATA_RULES, format_untrusted_context
from ..providers.base import LLMRequest
from ..schemas import Category, EpistemicStatus, FactSheet
from .checklists import Domain, checklist_text
from .context import AnalysisContext

MAX_FINDINGS_A = 12
MAX_MISSED_B = 6
MAX_FINDINGS_C = 18
MAX_NEW_IN_SYNTHESIS = 3

FINDING_EXAMPLE: dict[str, Any] = {
    "title": "Hosting cost is capped but traffic is unknown",
    "category": "missing_assumption",
    "perspective": "cost",
    "explanation": "The plan fixes a monthly hosting budget but gives no expected user volume.",
    "why_it_matters": "If usage is higher than assumed the budget could be exceeded within weeks.",
    "citations": [{"chunk_id": "d1-c2", "quote": "hosting budget is capped"}],
    "epistemic_status": "reasonable_inference",
    "impact": 7,
    "likelihood": 6,
    "urgency": 5,
    "recommended_action": "Estimate peak and average usage and price it against the cap.",
    "critical_question": "What usage level makes the hosting cap insufficient?",
    "why_overlooked": "Budgets are set before traffic forecasts exist, so the cap feels settled once written down.",
}

CATEGORY_HELP = {
    Category.MISSING_ASSUMPTION: "something the plan relies on but never states or validates",
    Category.OVERLOOKED_CONSTRAINT: "a limit (time, money, people, law, technology) not acknowledged",
    Category.RISK: "a concrete way the project could fail or be harmed",
    Category.MISSING_DEPENDENCY: "something external or internal the work needs that is not planned for",
    Category.CONTRADICTION: "two parts of the material that conflict with each other",
    Category.MISSING_INFORMATION: "important information that is absent or incomplete",
    Category.UNASKED_QUESTION: "an important question the authors do not appear to have asked",
    Category.OPPORTUNITY: "a realistic improvement the material overlooks",
}

STATUS_HELP = {
    EpistemicStatus.VERIFIED_FACT: "directly stated in the material (requires a citation with a quote)",
    EpistemicStatus.REASONABLE_INFERENCE: "follows from the material, or is based on what the material does not say",
    EpistemicStatus.UNVERIFIED_HYPOTHESIS: "plausible given the type of project, but not supported by the material",
}

SCORING_GUIDE = (
    "Scores are integers 1-10 and are YOUR JUDGEMENT, not measurements:\n"
    "- impact: damage to the project's goals if this materialises (1 trivial ... 10 project-ending).\n"
    "- likelihood: chance it materialises given what the material says (1 very unlikely ... 10 near certain).\n"
    "- urgency: how soon it must be addressed before it becomes costly (1 can wait ... 10 before anything else)."
)


def _enum_lines(mapping: dict) -> str:
    return "\n".join(f"  - {k.value}: {v}" for k, v in mapping.items())


def _finding_schema_text() -> str:
    return (
        "Each finding is a JSON object with exactly these keys: title, category, perspective, "
        "explanation, why_it_matters, citations, epistemic_status, impact, likelihood, urgency, "
        "recommended_action, critical_question, why_overlooked.\n"
        f"category must be one of:\n{_enum_lines(CATEGORY_HELP)}\n"
        f"epistemic_status must be one of:\n{_enum_lines(STATUS_HELP)}\n"
        "citations is a list of {\"chunk_id\": \"<id shown in the data>\", \"quote\": \"<short exact quote or null>\"}. "
        "Use only chunk_id values that appear in the data. A quote must be copied exactly from that chunk. "
        "Leave citations empty when the finding is about something absent, and say so in the explanation.\n"
        f"{SCORING_GUIDE}\n"
        f"Example finding:\n{json.dumps(FINDING_EXAMPLE, indent=2)}"
    )


QUALITY_BAR = (
    "QUALITY BAR (read before writing):\n"
    "- Specific, not generic. Every finding must name something concrete from THIS material (a number, date, "
    "name, component, sentence, column) or say exactly which expected element is missing. If a finding would "
    "make sense for any project of this type, delete it.\n"
    "- The title is a claim, not a topic. Good: \"A nightly CSV sync cannot meet a 24-hour delivery promise\". "
    "Bad: \"Delivery concerns\".\n"
    "- explanation (2-4 sentences): what the material says (quote the specifics) -> what is missing or in conflict "
    "-> the likely consequence.\n"
    "- why_overlooked (1 sentence): why a team in this position would probably miss it.\n"
    "- recommended_action: a concrete first step someone could start this week, not advice like \"consider "
    "security\" or \"follow best practices\".\n"
    "- critical_question: a question a named role could actually answer, mentioning the specifics.\n"
    "- Look across the material: compare numbers, dates, names and promises against each other for "
    "contradictions; for every goal ask what must be true for it to happen; for every number ask what it is "
    "based on; for every commitment ask who, by when, at what cost.\n"
    "- Use the whole 1-10 scale. At most two findings may have impact 9-10; several should be 3-6. Likelihood 8+ "
    "only when the material shows it is already happening or nearly certain.\n"
    "- Only do arithmetic with numbers that appear in the material, and show it in the explanation.\n"
    "- Prefer fewer, sharper findings over many weak ones."
)


def _common_rules() -> str:
    return (
        "Principles:\n"
        "- Your job is to find what the authors have NOT asked, decided or considered. Do not summarise the material.\n"
        "- Never invent facts, numbers, quotes or sources. If something is not in the material, say it is not stated.\n"
        "- Treat missing information as a POTENTIAL gap, not a definite mistake.\n"
        "- Do not give legal, financial or security conclusions; frame them as items to verify with a qualified person.\n"
        "- Be specific to this project. Avoid generic checklist items that would apply to any project.\n"
        "- Write in plain, direct language a busy project lead can act on.\n"
        "- Respond with a single JSON object and nothing else (no markdown fences, no commentary)."
    )


def _perspective_block(context: AnalysisContext) -> str:
    lines = [f"- {p.name}: {p.focus}" for p in context.perspectives]
    return "Perspectives that apply to this material (do not force a finding for each):\n" + "\n".join(lines)


def _material(context: AnalysisContext) -> str:
    note = ""
    if context.truncated:
        note = (f"\n[Note: {len(context.chunks)} of {context.total_chunks} sections are shown; "
                "the rest were omitted for size.]")
    return "PROJECT MATERIAL (untrusted data):\n" + format_untrusted_context(context.chunks) + note


def _compact_findings(findings: list[dict[str, Any]]) -> str:
    return json.dumps(findings, ensure_ascii=False, indent=1)


# ----------------------------------------------------------------------------- role A
def facts_request(context: AnalysisContext) -> LLMRequest:
    """Pass 1: read carefully and record what the material states, before hunting for gaps."""
    system = (
        "You are a meticulous reader preparing a fact sheet about a project for a reviewer. You record what "
        "the material STATES, accurately and with sources. You do not judge it yet.\n\n"
        "Principles:\n"
        "- Never invent or infer facts. Every fact must be something the material says.\n"
        "- Keep numbers, dates, names and units exactly as written.\n"
        "- Respond with a single JSON object and nothing else.\n\n"
        f"{UNTRUSTED_DATA_RULES}"
    )
    user = (
        "Produce a fact sheet:\n"
        "- project_summary: 2-4 sentences: what the project is, for whom, and the stated goal.\n"
        "- facts: up to 40 of the most decision-relevant statements: goals, commitments, numbers, dates, "
        "dependencies, stated assumptions, decisions already made, constraints, and (for datasets) key data facts "
        "such as row counts, empty cells and extreme values. Each fact: statement (one sentence), kind "
        "(goal | commitment | number | date | dependency | assumption | decision | constraint | data | other), "
        "citations ([{\"chunk_id\": \"<id shown>\", \"quote\": \"<short exact quote>\"}]).\n"
        "- open_items: things the material itself says are undecided, unknown or to be done later.\n\n"
        'Output format: {"project_summary": "...", "facts": [{"statement": "...", "kind": "number", '
        '"citations": [{"chunk_id": "d1-c1", "quote": "..."}]}], "open_items": ["..."]}\n\n'
        f"{_material(context)}"
    )
    return LLMRequest(system=system, user=user, temperature=0.1, max_tokens=6000)


def _facts_block(facts: FactSheet | None) -> str:
    if facts is None:
        return ""
    rows = [{"statement": f.statement, "kind": f.kind,
             "chunks": [c.chunk_id for c in f.citations]} for f in facts.facts]
    return (
        "WHAT THE MATERIAL STATES (a first-pass fact sheet; check it against the material and use it to spot "
        "conflicts and gaps):\n"
        f"Summary: {facts.project_summary}\n"
        f"Facts: {json.dumps(rows, ensure_ascii=False)}\n"
        f"Items the material itself leaves open: {json.dumps(facts.open_items, ensure_ascii=False)}\n\n"
    )


def analyst_request(context: AnalysisContext, facts: FactSheet | None = None,
                    domains: list[Domain] | None = None) -> LLMRequest:
    system = (
        "You are the lead analyst in a project-review engine called The Unasked Question Engine. "
        "You examine project documents, datasets and workflows and surface missing assumptions, "
        "overlooked constraints, hidden risks, missing dependencies, contradictions, missing "
        "information, critical unasked questions and improvement opportunities.\n\n"
        f"{_common_rules()}\n\n{QUALITY_BAR}\n\n{UNTRUSTED_DATA_RULES}"
    )
    probes = checklist_text(domains or [])
    user = (
        f"{_facts_block(facts)}"
        f"{_perspective_block(context)}\n\n"
        f"{probes + chr(10) + chr(10) if probes else ''}"
        f"{_finding_schema_text()}\n\n"
        f"Return at most {MAX_FINDINGS_A} findings, best first. Quality over quantity.\n"
        'Output format: {"findings": [ ...finding objects... ]}\n\n'
        f"{_material(context)}"
    )
    return LLMRequest(system=system, user=user, temperature=0.3, max_tokens=8000)


# ----------------------------------------------------------------------------- role B
def critic_request(context: AnalysisContext, candidates: list[dict[str, Any]]) -> LLMRequest:
    system = (
        "You are an independent reviewer. Another analyst produced candidate findings about a "
        "project. Challenge them honestly, and find important things they missed. You did not "
        "write them and have no reason to defend them.\n\n"
        f"{_common_rules()}\n\n{QUALITY_BAR}\n\n{UNTRUSTED_DATA_RULES}"
    )
    user = (
        "Tasks:\n"
        "1. challenges: for any candidate that is generic, weak, overstated, unsupported, duplicated or mis-scored (scores that "
        "ignore the 1-10 calibration above), "
        "give the candidate's exact title in finding_title, your objection, and optionally suggested_adjustment.\n"
        f"2. missed_findings (at most {MAX_MISSED_B}): important findings the analyst missed (use the finding schema "
        "below). Look especially for contradictions between different parts of the material, second-order "
        "effects, and assumptions everyone shares so nobody states them. Only include genuinely important, "
        "project-specific items.\n"
        "3. missing_questions: important questions the project team has not asked.\n\n"
        f"Finding schema for missed_findings:\n{_finding_schema_text()}\n\n"
        'Output format: {"challenges": [{"finding_title": "...", "objection": "...", '
        '"suggested_adjustment": "... or null"}], "missed_findings": [...], "missing_questions": ["..."]}\n\n'
        f"CANDIDATE FINDINGS (from the analyst):\n{_compact_findings(candidates)}\n\n"
        f"{_perspective_block(context)}\n\n{_material(context)}"
    )
    return LLMRequest(system=system, user=user, temperature=0.4, max_tokens=7000)


# ----------------------------------------------------------------------------- role C
def synthesis_request(context: AnalysisContext, candidates: list[dict[str, Any]],
                      challenges: list[dict[str, Any]], questions: list[str]) -> LLMRequest:
    system = (
        "You are the final validator and editor of a project-review engine. You receive candidate "
        "findings from several analysts, a reviewer's challenges, and the original material. "
        "Produce the final, de-duplicated, evidence-checked list.\n\n"
        f"{_common_rules()}\n\n{QUALITY_BAR}\n\n{UNTRUSTED_DATA_RULES}"
    )
    user = (
        "Tasks:\n"
        "- Merge duplicates. For a merged finding list the exact titles of the candidates it replaces in merged_from.\n"
        "- Check each finding against the material. Remove findings the material contradicts. "
        "Lower epistemic_status (verified_fact -> reasonable_inference -> unverified_hypothesis) when support is weaker than claimed. "
        "Keep citations only if the chunk really supports the finding.\n"
        "- Apply reviewer challenges that are justified (adjust text, scores or status). "
        "When analysts or the reviewer disagree materially, keep the finding and describe the disagreement in disagreement_note.\n"
        "- validation_note: one short sentence on how well the evidence supports the finding.\n"
        f"- You may add at most {MAX_NEW_IN_SYNTHESIS} brand-new findings, only if they are important, specific, "
        "supported by the material, and missed by everyone else (for example a contradiction between two "
        "candidates' sources). Otherwise only merge, correct or remove.\n"
        "- Remove or sharpen findings that are generic. Keep why_overlooked and make it concrete.\n"
        "- Re-calibrate scores across the whole list so they are comparable and use the full 1-10 range "
        "(at most two findings with impact 9-10).\n"
        f"- Return at most {MAX_FINDINGS_C} findings, most important first.\n"
        "- unanswered_questions: the most important questions the team has not asked (max 15, most important first).\n"
        "- overall_summary: 3-5 plain sentences (no markdown) on the project's main blind spots.\n\n"
        "Each final finding uses the finding schema below plus optional keys merged_from (list of titles), "
        "disagreement_note and validation_note.\n"
        f"{_finding_schema_text()}\n\n"
        'Output format: {"findings": [...], "unanswered_questions": ["..."], "overall_summary": "..."}\n\n'
        f"CANDIDATE FINDINGS:\n{_compact_findings(candidates)}\n\n"
        f"REVIEWER CHALLENGES:\n{_compact_findings(challenges)}\n\n"
        f"REVIEWER QUESTIONS:\n{_compact_findings([{'question': q} for q in questions])}\n\n"
        f"{_material(context)}"
    )
    return LLMRequest(system=system, user=user, temperature=0.2, max_tokens=8192)
