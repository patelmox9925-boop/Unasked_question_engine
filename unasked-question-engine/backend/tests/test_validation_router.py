import json

import pytest

from app.providers.base import LLMRequest, ProviderError, ProviderErrorKind
from app.providers.mock import MockProvider
from app.providers.router import AllProvidersFailed, LLMRouter
from app.providers.validation import SchemaValidationError, extract_json_object, parse_model_output
from app.schemas import AnalysisOutput, CritiqueOutput, SynthesisOutput
from tests.conftest import make_settings

REQ = LLMRequest(system="s", user="u")


def finding(**over):
    base = dict(
        title="Hosting budget not validated", category="missing_assumption", perspective="cost",
        explanation="The plan assumes 500 USD/month will cover hosting.",
        why_it_matters="Overruns could stall launch.",
        citations=[{"chunk_id": "d1-c1", "quote": "capped at 500"}],
        epistemic_status="reasonable_inference", impact=7, likelihood=6, urgency=5,
        recommended_action="Get a vendor quote.", critical_question="What happens at 2x traffic?",
    )
    base.update(over)
    return base


def analysis_json(**over):
    return json.dumps({"findings": [finding(**over)]})


# ----------------------------------------------------------------- JSON extraction
def test_extract_json_variants():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Sure! Here you go:\n{"a": {"b": 2}}\nHope that helps') == {"a": {"b": 2}}


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2, 3]", '{"unterminated": ', "```\nnot json\n```"])
def test_extract_json_failures(raw):
    with pytest.raises(SchemaValidationError):
        extract_json_object(raw)


# ----------------------------------------------------------------- strict schemas
def test_valid_analysis_parses():
    out = parse_model_output(analysis_json(), AnalysisOutput)
    assert out.findings[0].impact == 7 and out.findings[0].citations[0].chunk_id == "d1-c1"


@pytest.mark.parametrize("override", [
    {"impact": 11}, {"impact": 0}, {"likelihood": "high"}, {"category": "vibes"},
    {"epistemic_status": "certain"}, {"title": ""}, {"recommended_action": None},
    {"unexpected_field": "x"},  # extra="forbid"
])
def test_invalid_findings_rejected(override):
    with pytest.raises(SchemaValidationError):
        parse_model_output(analysis_json(**override), AnalysisOutput)


def test_missing_required_field_rejected_with_location():
    bad = finding()
    del bad["critical_question"]
    with pytest.raises(SchemaValidationError) as exc:
        parse_model_output(json.dumps({"findings": [bad]}), AnalysisOutput)
    assert "findings.0.critical_question" in exc.value.message


def test_extra_top_level_keys_rejected():
    with pytest.raises(SchemaValidationError):
        parse_model_output(json.dumps({"findings": [], "note": "hi"}), AnalysisOutput)


def test_critique_and_synthesis_schemas():
    crit = {"challenges": [{"finding_title": "X", "objection": "Weak evidence"}],
            "missed_findings": [finding()], "missing_questions": ["Who owns on-call?"]}
    assert parse_model_output(json.dumps(crit), CritiqueOutput).missing_questions == ["Who owns on-call?"]
    synth = {"findings": [dict(finding(), merged_from=["A", "B"], disagreement_note="A rated 8, B rated 4")],
             "unanswered_questions": ["q"], "overall_summary": "Summary."}
    assert parse_model_output(json.dumps(synth), SynthesisOutput).findings[0].merged_from == ["A", "B"]
    with pytest.raises(SchemaValidationError):
        parse_model_output(json.dumps({"findings": []}), SynthesisOutput)  # summary required


# ----------------------------------------------------------------- router
def routed_settings(**over):
    base = dict(
        llm_a_provider="groq", llm_a_model="primary-model",
        llm_a_fallback_provider="deepseek", llm_a_fallback_model="fallback-model",
        groq_api_key="ant-key-aaaaaaaaaaaa", deepseek_api_key="oa-key-aaaaaaaaaaaa",
    )
    base.update(over)
    return make_settings(**base)


def router_with(settings, **providers):
    return LLMRouter(settings, provider_factory=lambda name: providers[name])


async def test_primary_success_makes_a_single_call():
    a = MockProvider("groq", [analysis_json()])
    b = MockProvider("deepseek", [analysis_json()])
    result = await router_with(routed_settings(), groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    assert result.provider == "groq" and not result.used_fallback and result.consulted
    assert len(a.calls) == 1 and len(b.calls) == 0
    assert [x.ok for x in result.attempts] == [True]


async def test_fallback_used_when_primary_fails_and_failure_is_recorded():
    err = ProviderError("groq", ProviderErrorKind.RATE_LIMIT, "429", retryable=True)
    a = MockProvider("groq", [err])
    b = MockProvider("deepseek", [analysis_json()])
    result = await router_with(routed_settings(), groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    assert result.provider == "deepseek" and result.used_fallback and result.model == "fallback-model"
    assert [(x.provider, x.ok) for x in result.attempts] == [("groq", False), ("deepseek", True)]
    assert result.attempts[0].error_kind == "rate_limit"


async def test_schema_repair_succeeds_on_second_call_same_provider():
    a = MockProvider("groq", ["this is not json", analysis_json()])
    b = MockProvider("deepseek", [])
    result = await router_with(routed_settings(), groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    assert result.provider == "groq" and len(a.calls) == 2
    assert "rejected by the validator" in a.calls[1][0].user and a.calls[1][0].user.startswith("u")
    assert [(x.ok, x.is_repair) for x in result.attempts] == [(False, False), (True, True)]


async def test_schema_failure_after_repair_falls_back():
    a = MockProvider("groq", ["bad", '{"findings": "nope"}'])
    b = MockProvider("deepseek", [analysis_json()])
    result = await router_with(routed_settings(), groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    assert result.provider == "deepseek" and len(a.calls) == 2


async def test_repairs_can_be_disabled():
    a = MockProvider("groq", ["bad"])
    b = MockProvider("deepseek", [analysis_json()])
    s = routed_settings(llm_max_schema_repairs=0)
    result = await router_with(s, groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    assert len(a.calls) == 1 and result.provider == "deepseek"


async def test_all_providers_fail_raises_without_fabricating():
    errs = [ProviderError("groq", ProviderErrorKind.TIMEOUT, "t"),
            ProviderError("deepseek", ProviderErrorKind.AUTH, "a")]
    a, b = MockProvider("groq", [errs[0]]), MockProvider("deepseek", [errs[1]])
    with pytest.raises(AllProvidersFailed) as exc:
        await router_with(routed_settings(), groq=a, deepseek=b).run("A", REQ, AnalysisOutput)
    failure = exc.value
    assert not any(x.ok for x in failure.attempts) and len(failure.attempts) == 2
    assert "No analysis was produced" in failure.message
    assert "groq/primary-model: timeout" in failure.message and "deepseek/fallback-model: auth" in failure.message


async def test_unconfigured_role_gives_clear_error():
    router = LLMRouter(make_settings())
    with pytest.raises(AllProvidersFailed) as exc:
        await router.run("B", REQ, AnalysisOutput)
    assert "LLM_B_PROVIDER" in exc.value.message and not router.role_available("B")


async def test_missing_key_primary_skips_to_fallback_without_network():
    s = routed_settings(groq_api_key=None)
    # Use the real factory: the keyless provider must fail locally (NOT_CONFIGURED)
    fallback = MockProvider("deepseek", [analysis_json()])
    from app.providers import build_provider

    def factory(name):
        return fallback if name == "deepseek" else build_provider(name, s)

    result = await LLMRouter(s, provider_factory=factory).run("A", REQ, AnalysisOutput)
    assert result.used_fallback and result.attempts[0].error_kind == "not_configured"


async def test_identical_fallback_is_not_called_twice():
    s = routed_settings(llm_a_fallback_provider="groq", llm_a_fallback_model="primary-model")
    a = MockProvider("groq", [ProviderError("groq", ProviderErrorKind.SERVER, "boom")])
    with pytest.raises(AllProvidersFailed):
        await router_with(s, groq=a).run("A", REQ, AnalysisOutput)
    assert len(a.calls) == 1


async def test_roles_route_to_their_own_configured_models():
    s = routed_settings(llm_b_provider="gemini", llm_b_model="b-model", gemini_api_key="g-key-aaaaaaaaaaaa")
    gem = MockProvider("gemini", [json.dumps({"challenges": [], "missed_findings": [], "missing_questions": []})])
    result = await router_with(s, gemini=gem, groq=MockProvider("groq")).run("B", REQ, CritiqueOutput)
    assert (result.role, result.provider, result.model) == ("B", "gemini", "b-model")


async def test_invalid_role_rejected():
    with pytest.raises(ValueError):
        await LLMRouter(make_settings()).run("Q", REQ, AnalysisOutput)
