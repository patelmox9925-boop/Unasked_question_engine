import pytest

from app.analysis.pipeline import AnalysisFailed, AnalysisPipeline
from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.mock import MockProvider
from app.schemas import EpistemicStatus, PriorityLevel
from tests.helpers import (
    FULL_ROLES,
    analysis_json,
    critique_json,
    facts_json,
    finding,
    project_from,
    router_for,
    synthesis_json,
)

F_COST = finding()
F_PASSWORD = finding(
    title="Shared password is the only login control", category="risk", perspective="security",
    explanation="Users log in with a shared password.", why_it_matters="Shared credentials cannot be revoked per person.",
    citations=[{"chunk_id": "desc-c1", "quote": "Users log in with a shared password"}],
    epistemic_status="verified_fact", impact=9, likelihood=8, urgency=8,
    recommended_action="Introduce individual accounts.", critical_question="How will access be revoked when someone leaves?",
)
F_FAKE = finding(
    title="Vendor lock-in with an unnamed provider", category="risk", epistemic_status="verified_fact",
    citations=[{"chunk_id": "desc-c42", "quote": "we are locked in"}], impact=6, likelihood=5, urgency=4,
)


def err(provider, kind=ProviderErrorKind.SERVER):
    return ProviderError(provider, kind, f"{provider} down", retryable=False)


def mocks(a=None, b=None, c=None):
    return {"groq": MockProvider("groq", a or []), "deepseek": MockProvider("deepseek", b or []),
            "gemini": MockProvider("gemini", c or [])}


async def run(providers, project=None, **settings_over):
    router, _ = router_for(providers, **settings_over)
    events = []
    result = await AnalysisPipeline(router).run(project or project_from(),
                                                lambda k, s, d: events.append((k, s)))
    return result, events


async def test_full_three_model_pipeline():
    synth = [dict(F_PASSWORD, merged_from=["Shared password is the only login control"],
                  validation_note="Quote confirmed.", disagreement_note="B thought impact was lower."),
             dict(F_COST, merged_from=["Hosting cost is capped but traffic is unknown"], citations=[])]
    p = mocks(
        a=[facts_json(), analysis_json(F_COST, F_PASSWORD, F_FAKE)],
        b=[critique_json(challenges=[{"finding_title": F_FAKE["title"], "objection": "No evidence."}],
                         missed=[finding(title="No on-call owner named", category="missing_dependency", citations=[])],
                         questions=["Who is on call after launch?"])],
        c=[synthesis_json(synth, questions=["Who owns incident response?"], summary="Access control and cost are blind spots.")],
    )
    result, events = await run(p)

    assert [f.id for f in result.findings] == ["f1", "f2"]
    top, second = result.findings
    assert top.title.startswith("Shared password") and top.priority_level == PriorityLevel.CRITICAL
    assert top.epistemic_status == EpistemicStatus.VERIFIED_FACT and top.evidence[0].quote_verified
    assert top.raised_by == ["A (groq/model-a)", "C (gemini/model-c)"]
    assert top.disagreement_note == "B thought impact was lower."
    # C dropped the citations on the cost finding; they are inherited from A's candidate and re-verified
    assert second.evidence and second.evidence[0].chunk_id == "desc-c1"
    assert result.unanswered_questions == ["Who owns incident response?"]
    assert result.overall_summary == "Access control and cost are blind spots."
    assert result.origin == "llm" and result.risk_summary.overall_level == PriorityLevel.CRITICAL
    assert [(m.role, m.succeeded) for m in result.models_consulted] == [("A", True), ("B", True), ("C", True)]
    assert result.warnings == []
    assert [e for e in events if e[1] in ("done", "skipped", "failed")] == [
        ("extract", "done"), ("context", "done"), ("facts", "done"), ("analysis", "done"), ("critique", "done"),
        ("synthesis", "done"), ("prioritize", "done")]
    # each role is called once (A twice: fact sheet, then gap analysis)
    assert [len(p[n].calls) for n in ("groq", "deepseek", "gemini")] == [2, 1, 1]
    # C is told about B's objections and B saw A's candidates
    assert "No evidence." in p["gemini"].calls[0][0].user and F_COST["title"] in p["deepseek"].calls[0][0].user


async def test_only_model_a_configured_skips_b_and_c_with_visible_warning():
    p = mocks(a=[facts_json(), analysis_json(F_COST, F_FAKE)])
    router, _ = router_for(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    events = []
    result = await AnalysisPipeline(router).run(project_from(), lambda k, s, d: events.append((k, s)))
    assert ("critique", "skipped") in events and ("synthesis", "skipped") in events
    assert [m.role for m in result.models_consulted] == ["A"]
    assert any("Model C is not configured" in w and "deterministic" in w for w in result.warnings)
    assert result.overall_summary is None
    assert F_COST["critical_question"] in result.unanswered_questions
    # fabricated evidence is gone and the finding is honestly labelled
    fake = next(f for f in result.findings if f.title.startswith("Vendor"))
    assert not any(e.kind == "cited" for e in fake.evidence)  # nothing the model claimed survived
    assert fake.epistemic_status == EpistemicStatus.UNVERIFIED_HYPOTHESIS


async def test_model_a_failure_raises_and_fabricates_nothing():
    p = mocks(a=[err("groq")])
    router, _ = router_for(p)
    with pytest.raises(AnalysisFailed) as exc:
        await AnalysisPipeline(router).run(project_from())
    assert "No analysis was produced" in exc.value.message
    assert [(m.role, m.succeeded) for m in exc.value.models] == [("A", False)]
    assert not p["deepseek"].calls and not p["gemini"].calls  # B and C never called


async def test_model_b_failure_degrades_with_warning_and_c_still_runs():
    p = mocks(a=[facts_json(), analysis_json(F_COST)], b=[err("deepseek", ProviderErrorKind.AUTH)],
              c=[synthesis_json([dict(F_COST, merged_from=[])])])
    result, events = await run(p)
    assert ("critique", "failed") in events and ("synthesis", "done") in events
    assert any("Model B" in w and "unavailable" in w for w in result.warnings)
    b = next(m for m in result.models_consulted if m.role == "B")
    assert b.succeeded is False  # never claimed as consulted
    assert next(m for m in result.models_consulted if m.role == "C").succeeded is True


async def test_model_c_failure_falls_back_to_deterministic_merge():
    dup = dict(F_COST, impact=3, likelihood=2)
    p = mocks(a=[facts_json(), analysis_json(F_COST)],
              b=[critique_json(challenges=[{"finding_title": F_COST["title"], "objection": "Overstated."}],
                               missed=[dup], questions=["What is the traffic?"])],
              c=[err("gemini", ProviderErrorKind.RATE_LIMIT)])
    result, _ = await run(p)
    assert len(result.findings) == 1  # A's and B's duplicate merged
    f = result.findings[0]
    assert set(f.raised_by) == {"A (groq/model-a)", "B (deepseek/model-b)"}
    assert "Reviewer B (deepseek/model-b) objected: Overstated." in f.disagreement_note
    assert "scored this differently" in f.disagreement_note
    assert any("Model C" in w and "unavailable" in w for w in result.warnings)
    assert result.unanswered_questions[0] == "What is the traffic?"
    c = next(m for m in result.models_consulted if m.role == "C")
    assert c.succeeded is False


async def test_fallback_provider_is_recorded():
    p = mocks(a=[err("groq"), err("groq")], b=[facts_json(), analysis_json(F_COST)])  # deepseek is A's fallback here
    result, _ = await run(p, llm_a_fallback_provider="deepseek", llm_a_fallback_model="fallback-a",
                          llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    a_entries = [(m.provider, m.succeeded, m.used_as_fallback) for m in result.models_consulted]
    assert a_entries == [("groq", False, False), ("deepseek", True, True)]  # both A calls fell back


async def test_empty_but_valid_analysis_is_reported_honestly():
    p = mocks(a=[facts_json(), analysis_json()], b=[critique_json()])
    result, events = await run(p)
    assert result.findings == [] and ("synthesis", "skipped") in events
    assert any("no findings" in w.lower() for w in result.warnings)
    assert result.risk_summary.overall_level == PriorityLevel.LOW and not p["gemini"].calls


async def test_synthesis_introduced_findings_are_flagged():
    new = finding(title="Completely new topic from synthesis step", category="opportunity", citations=[])
    p = mocks(a=[facts_json(), analysis_json(F_COST)], b=[critique_json()], c=[synthesis_json([new])])
    result, _ = await run(p)
    assert any("first appeared in the synthesis step" in w for w in result.warnings)


async def test_findings_capped_and_ranked_best_first():
    many = [finding(title=f"Distinct topic number {i} {'x' * i}", impact=1 + (i % 10), likelihood=5, citations=[])
            for i in range(15)]
    p = mocks(a=[facts_json(), analysis_json(*many)])
    result, _ = await run(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="")
    scores = [f.priority_score for f in result.findings]
    assert scores == sorted(scores, reverse=True) and len(result.findings) == 15
    assert result.findings[0].id == "f1" and result.findings[-1].id == "f15"
    assert FULL_ROLES  # keep import used
