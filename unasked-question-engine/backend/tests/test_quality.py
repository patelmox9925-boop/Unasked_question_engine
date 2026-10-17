import pytest

from app.analysis import prompts
from app.analysis.checklists import checklist_text, detect_domains
from app.analysis.context import build_context
from app.analysis.pipeline import AnalysisFailed, MAX_CANDIDATES_TO_SYNTHESIS
from app.analysis.quality import (
    Material,
    attach_related_evidence,
    calibration_warning,
    drop_generic,
    is_generic,
)
from app.extraction.parsers import parse_text
from app.providers.base import ProviderError, ProviderErrorKind
from app.schemas import EpistemicStatus, Finding, PriorityLevel
from tests.helpers import (
    TEXT,
    analysis_json,
    critique_json,
    facts_json,
    finding,
    project_from,
    synthesis_json,
)
from tests.test_pipeline import err, mocks, run

PLAN = (
    "# Harvest Box\n\nWe launch a meal kit app in March with two engineers.\n\n"
    "## Fulfilment\nOrders sync with the warehouse through a nightly CSV export. Every order is promised "
    "delivery within 24 hours.\n\n## Budget\nHosting is capped at 500 dollars per month.\n\n"
    "## Support\nFounders handle customer support.\n"
)


def f(**over) -> Finding:
    base = dict(id="f1", title="T", category="risk", explanation="e", why_it_matters="w", evidence=[],
                epistemic_status="reasonable_inference", impact=5, likelihood=5, urgency=5,
                recommended_action="a", critical_question="q")
    base.update(over)
    return Finding(**base)


# ------------------------------------------------------------------ generic-finding filter
def test_generic_findings_without_evidence_are_detected():
    chunks = parse_text(PLAN, "plan.md", "d1", markdown=True).chunks
    material = Material(chunks)
    generic = f(title="Consider security best practices", explanation="Follow industry standard best practice "
                "going forward.", critical_question="Is the plan robust?")
    specific = f(title="Nightly CSV export cannot meet the 24-hour delivery promise",
                 explanation="Orders sync nightly, yet delivery is promised within 24 hours.",
                 critical_question="What is the latest order time for 24-hour delivery?")
    assert is_generic(generic, material) and not is_generic(specific, material)


def test_cited_findings_are_never_called_generic():
    chunks = parse_text(PLAN, "plan.md", "d1", markdown=True).chunks
    cited = f(title="Best practice", explanation="ensure scalability", evidence=[
        {"chunk_id": "d1-c1", "source_label": "s", "filename": "plan.md", "excerpt": "x", "quote_verified": True}])
    assert not is_generic(cited, Material(chunks))


def test_drop_generic_keeps_everything_when_it_would_leave_too_little():
    chunks = parse_text(PLAN, "plan.md", "d1", markdown=True).chunks
    generic = [f(id=f"g{i}", title=f"Consider best practices {i}", explanation="industry standard going forward",
                 critical_question="Is it robust?") for i in range(2)]
    kept, dropped = drop_generic(generic, chunks)
    assert len(kept) == 2 and dropped == 0
    specific = [f(id=f"s{i}", title=f"Nightly CSV export problem {i}", explanation="nightly warehouse export 24-hour",
                  critical_question="warehouse delivery?") for i in range(3)]
    kept, dropped = drop_generic(specific + generic, chunks)
    assert dropped == 2 and {x.id for x in kept} == {"s0", "s1", "s2"}


# ------------------------------------------------------------------ related passages
def test_related_passages_are_attached_to_uncited_findings_and_labelled():
    chunks = parse_text(PLAN, "plan.md", "d1", markdown=True).chunks
    gap = f(title="Who covers customer support after launch?", category="missing_dependency",
            explanation="Founders handle customer support; hours and coverage are not stated.",
            critical_question="Who answers support requests at the weekend?")
    cited = f(id="f2", title="Hosting cost", evidence=[
        {"chunk_id": "d1-c1", "source_label": "s", "filename": "plan.md", "excerpt": "x", "quote_verified": True}])
    unrelated = f(id="f3", title="Zebra crossing", explanation="giraffe", critical_question="okapi?")
    assert attach_related_evidence([gap, cited, unrelated], chunks) == 1
    assert len(gap.evidence) >= 1 and all(e.kind == "related" and not e.quote_verified for e in gap.evidence)
    assert "support" in gap.evidence[0].excerpt.lower() and len(gap.evidence[0].excerpt) <= 281
    assert cited.evidence[0].kind == "cited" and unrelated.evidence == []
    assert gap.epistemic_status == EpistemicStatus.REASONABLE_INFERENCE  # related text is not proof


def test_calibration_warning_only_when_scores_cluster_high():
    high = [f(id=str(i), priority_level=PriorityLevel.HIGH) for i in range(6)]
    mixed = [f(id=str(i), priority_level=PriorityLevel.HIGH if i < 2 else PriorityLevel.LOW) for i in range(6)]
    assert "discriminating" in calibration_warning(high)
    assert calibration_warning(mixed) is None and calibration_warning(high[:3]) is None


# ------------------------------------------------------------------ checklists and prompts
def test_domain_detection_and_probe_text():
    chunks = parse_text(PLAN + "\nThe API and database run in the cloud with a login.", "p.md", "d1", markdown=True).chunks
    keys = [d.key for d in detect_domains(chunks)]
    assert "business" in keys or "operations" in keys
    assert detect_domains(parse_text("Hello there.", "n.txt", "d2").chunks) == []
    assert checklist_text([]) == ""
    text = checklist_text(detect_domains(chunks))
    assert "PROBE AREAS" in text and "raise one only if" in text


def test_prompts_carry_the_quality_bar_facts_and_probes():
    project = project_from(PLAN)
    ctx = build_context(project.chunks, [])
    from app.schemas import FactSheet
    facts = FactSheet(project_summary="A meal kit app.", facts=[{"statement": "Launch in March.", "kind": "date"}])
    req = prompts.analyst_request(ctx, facts, detect_domains(project.chunks))
    assert "QUALITY BAR" in req.system and "Specific, not generic" in req.system
    assert "WHAT THE MATERIAL STATES" in req.user and "Launch in March." in req.user
    assert "PROBE AREAS" in req.user and "why_overlooked" in req.user
    assert "WHAT THE MATERIAL STATES" not in prompts.analyst_request(ctx).user
    assert "fact sheet" in prompts.facts_request(ctx).system.lower()
    assert f"at most {prompts.MAX_FINDINGS_C}" in prompts.synthesis_request(ctx, [], [], []).user


# ------------------------------------------------------------------ pipeline behaviour
async def test_fact_sheet_becomes_verified_understanding_and_is_fed_to_the_analyst():
    p = mocks(a=[facts_json(open_items=["Hosting provider undecided"]), analysis_json(finding())])
    result, events = await run(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    u = result.understanding
    assert u and u.summary and u.open_items == ["Hosting provider undecided"]
    assert u.facts[0].evidence[0].quote_verified and u.facts[0].evidence[0].chunk_id == "desc-c1"
    assert ("facts", "done") in events
    assert "Hosting budget is capped at 500 dollars per month." in p["groq"].calls[1][0].user


async def test_unusable_fact_sheet_degrades_with_a_warning_but_analysis_continues():
    p = mocks(a=["not json", "still not json", analysis_json(finding())])
    result, events = await run(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    assert result.understanding is None and ("facts", "skipped") in events
    assert any("fact-sheet step could not be completed" in w for w in result.warnings)
    assert result.findings


async def test_outage_during_fact_sheet_fails_the_analysis_without_a_second_call():
    p = mocks(a=[err("groq", ProviderErrorKind.AUTH)])
    with pytest.raises(AnalysisFailed):
        await run(p)
    assert len(p["groq"].calls) == 1


async def test_why_overlooked_is_carried_through():
    p = mocks(a=[facts_json(), analysis_json(finding(why_overlooked="Budgets feel settled once written down."))])
    result, _ = await run(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    assert result.findings[0].why_overlooked == "Budgets feel settled once written down."


async def test_generic_padding_is_removed_with_a_warning():
    pad = [finding(title=f"Consider best practices item {i}", explanation="Follow industry standard going forward.",
                   critical_question="Is it robust?", citations=[]) for i in range(2)]
    good = [finding(title=f"Hosting budget problem {i}", explanation="hosting budget capped 500 dollars month",
                    critical_question="What usage breaks the budget?", citations=[]) for i in range(3)]
    p = mocks(a=[facts_json(), analysis_json(*pad, *good)])
    result, _ = await run(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    assert len(result.findings) == 3 and any("generic" in w for w in result.warnings)


async def test_each_role_gets_a_context_sized_for_its_provider():
    big = "\n\n".join(f"## Section {i}\n" + ("Detail about topic %d. " % i) * 120 for i in range(30))
    p = mocks(a=[facts_json(), analysis_json(finding(citations=[]))],
              b=[critique_json()], c=[synthesis_json([dict(finding(citations=[]), merged_from=[])])])
    result, _ = await run(p, project=project_from(big), groq_context_chars=40000, deepseek_context_chars=9000,
                          gemini_context_chars=20000)
    sizes = {name: len(p[name].calls[0][0].user) for name in ("groq", "deepseek", "gemini")}
    assert sizes["deepseek"] < sizes["gemini"] < sizes["groq"]  # A (groq) gets the biggest slice, B (deepseek) the smallest
    assert sum("were sent to the models" in w for w in result.warnings) >= 1


async def test_synthesis_receives_a_capped_best_first_candidate_list():
    many = [finding(title=f"Distinct topic {i} hosting", impact=1 + i % 10, citations=[]) for i in range(40)]
    p = mocks(a=[facts_json(), analysis_json(*many[:12])],
              b=[critique_json(missed=many[12:18])],
              c=[synthesis_json([dict(many[0], merged_from=[])])])
    await run(p)
    import json as _json
    user = p["gemini"].calls[0][0].user
    assert user.count('"raised_by"') <= MAX_CANDIDATES_TO_SYNTHESIS
