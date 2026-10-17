"""Shared builders for pipeline / API tests."""

from __future__ import annotations

import json

from app.extraction.parsers import parse_text
from app.providers import build_provider  # noqa: F401  (re-exported for convenience)
from app.providers.router import LLMRouter
from app.store import Project, ProjectStore
from tests.conftest import make_settings

TEXT = (
    "# Plan\n"
    "Hosting budget is capped at 500 dollars per month.\n\n"
    "We launch in March with two engineers. Users log in with a shared password.\n"
)


def project_from(text: str = TEXT) -> Project:
    doc = parse_text(text, "Project description", "desc", markdown=True, kind="description")
    return ProjectStore().create([doc], [], True)


def finding(**over):
    base = dict(
        title="Hosting cost is capped but traffic is unknown", category="missing_assumption",
        perspective="cost",
        explanation="The plan fixes a hosting budget without expected usage.",
        why_it_matters="Usage above the assumption could exceed the cap quickly.",
        citations=[{"chunk_id": "desc-c1", "quote": "capped at 500 dollars"}],
        epistemic_status="reasonable_inference", impact=7, likelihood=6, urgency=5,
        recommended_action="Estimate usage and price it against the cap.",
        critical_question="What usage makes the cap insufficient?",
    )
    base.update(over)
    return base


def facts_json(summary="A small web project with a capped hosting budget.", facts=None, open_items=()) -> str:
    facts = facts if facts is not None else [
        {"statement": "Hosting budget is capped at 500 dollars per month.", "kind": "number",
         "citations": [{"chunk_id": "desc-c1", "quote": "capped at 500 dollars"}]}]
    return json.dumps({"project_summary": summary, "facts": facts, "open_items": list(open_items)})


def analysis_json(*findings) -> str:
    return json.dumps({"findings": list(findings)})


def critique_json(challenges=(), missed=(), questions=()) -> str:
    return json.dumps({"challenges": list(challenges), "missed_findings": list(missed),
                       "missing_questions": list(questions)})


def synthesis_json(findings, questions=("Who is on call after launch?",), summary="Main blind spots are cost and access."):
    return json.dumps({"findings": list(findings), "unanswered_questions": list(questions),
                       "overall_summary": summary})


def chat_json(answer="Answer.", citations=(), finding_ids=(), grounding="grounded") -> str:
    return json.dumps({"answer": answer, "citations": list(citations),
                       "finding_ids": list(finding_ids), "grounding": grounding})


FULL_ROLES = dict(
    llm_a_provider="groq", llm_a_model="model-a", groq_api_key="ant-key-aaaaaaaaaaaa",
    llm_b_provider="deepseek", llm_b_model="model-b", deepseek_api_key="oa-key-aaaaaaaaaaaaaa",
    llm_c_provider="gemini", llm_c_model="model-c", gemini_api_key="g-key-aaaaaaaaaaaaaaa",
)


def router_for(providers: dict, **settings_over) -> tuple[LLMRouter, object]:
    roles = dict(FULL_ROLES)
    roles.update(settings_over)
    settings = make_settings(**roles)
    return LLMRouter(settings, provider_factory=lambda name: providers[name]), settings
