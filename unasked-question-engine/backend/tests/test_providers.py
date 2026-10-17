import json

import httpx
import pytest

from app.providers import PROVIDER_CLASSES, build_provider
from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.base import LLMRequest, ProviderError, ProviderErrorKind
from app.providers.gemini_provider import GeminiProvider
from app.providers.groq_provider import GroqProvider
from tests.conftest import make_settings

REQ = LLMRequest(system="sys prompt", user="user prompt", max_tokens=100)
KEY = "sk-test-key-0123456789abcdefghij"

OPENAI_OK = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
             "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7}}


def make(cls, handler, *, retries=2, key=KEY, sleeps=None):
    sleeps = sleeps if sleeps is not None else []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = cls(api_key=key, base_url="https://api.test/v1", client=client, max_retries=retries,
                   backoff_base=0.1, max_retry_delay=5, sleep=fake_sleep)
    return provider, sleeps


# ----------------------------------------------------------------- request building / parsing
async def test_groq_request_and_response():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx.Response(200, json=OPENAI_OK)

    provider, _ = make(GroqProvider, handler)
    out = await provider.generate(REQ, "model-x")
    assert seen["url"] == "https://api.test/v1/chat/completions"
    assert seen["headers"]["authorization"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "model-x" and seen["body"]["max_completion_tokens"] == 100
    assert seen["body"]["temperature"] == REQ.temperature
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys prompt"}
    assert (out.text, out.provider, out.model, out.input_tokens, out.output_tokens) == ('{"ok": true}', "groq", "model-x", 11, 7)


async def test_deepseek_chat_request_uses_max_tokens_and_json_mode():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OPENAI_OK)

    provider, _ = make(DeepSeekProvider, handler)
    out = await provider.generate(REQ, "deepseek-chat")
    assert seen["body"]["max_tokens"] == 100 and "max_completion_tokens" not in seen["body"]
    assert seen["body"]["response_format"] == {"type": "json_object"} and out.provider == "deepseek"


async def test_deepseek_reasoner_omits_json_mode_and_temperature_and_strips_thinking():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '<think>hmm</think>{"ok": true}'}}]})

    provider, _ = make(DeepSeekProvider, handler)
    out = await provider.generate(REQ, "deepseek-reasoner")
    assert "response_format" not in seen["body"] and "temperature" not in seen["body"]
    assert out.text == '{"ok": true}'


async def test_output_tokens_are_clamped_to_the_provider_limit():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OPENAI_OK)

    provider, _ = make(GroqProvider, handler)
    await provider.generate(REQ.model_copy(update={"max_tokens": 99999}), "m")
    assert seen["body"]["max_completion_tokens"] == GroqProvider.max_output_tokens


@pytest.mark.parametrize("cls,payload,expected", [
    (GroqProvider, {"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]}, ["a-model", "b-model"]),
    (DeepSeekProvider, {"data": [{"id": "deepseek-chat"}]}, ["deepseek-chat"]),
    (GeminiProvider, {"models": [{"name": "models/g-1", "supportedGenerationMethods": ["generateContent"]},
                                 {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]}, ["g-1"]),
])
async def test_list_models_parses_each_provider(cls, payload, expected):
    seen = {}

    def handler(request):
        seen["method"], seen["url"] = request.method, str(request.url)
        return httpx.Response(200, json=payload)

    provider, _ = make(cls, handler)
    assert await provider.list_models() == expected
    assert seen["method"] == "GET" and KEY not in seen["url"]


async def test_list_models_reports_bad_keys_and_missing_keys():
    provider, _ = make(GroqProvider, lambda r: httpx.Response(401, text="bad"))
    with pytest.raises(ProviderError) as exc:
        await provider.list_models()
    assert exc.value.kind == ProviderErrorKind.AUTH
    provider, _ = make(GroqProvider, lambda r: httpx.Response(200, json={}), key=None)
    with pytest.raises(ProviderError) as exc:
        await provider.list_models()
    assert exc.value.kind == ProviderErrorKind.NOT_CONFIGURED


async def test_gemini_request_and_response():
    seen = {}

    def handler(request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx.Response(200, json=GEMINI_OK)

    provider, _ = make(GeminiProvider, handler)
    out = await provider.generate(REQ, "model-z")
    assert seen["url"] == "https://api.test/v1/models/model-z:generateContent"
    assert seen["headers"]["x-goog-api-key"] == KEY and KEY not in seen["url"]
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys prompt"
    assert out.text == '{"ok": true}' and out.input_tokens == 11


@pytest.mark.parametrize("cls,payload", [
    (GroqProvider, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}),
    (GroqProvider, {"choices": [{"message": {"refusal": "no"}}]}),
    (DeepSeekProvider, {"choices": [{"message": {"content": "<think>only thoughts</think>"}}]}),
    (GeminiProvider, {"candidates": []}),
    (GeminiProvider, {"promptFeedback": {"blockReason": "SAFETY"}}),
])
async def test_empty_or_blocked_responses_are_invalid(cls, payload):
    provider, _ = make(cls, lambda r: httpx.Response(200, json=payload))
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.INVALID_RESPONSE


async def test_malformed_payload_shape_is_invalid_response():
    provider, _ = make(GroqProvider, lambda r: httpx.Response(200, json={"unexpected": 1}))
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.INVALID_RESPONSE


async def test_non_json_body_is_invalid_response():
    provider, _ = make(GroqProvider, lambda r: httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.INVALID_RESPONSE


# ----------------------------------------------------------------- failure handling
async def test_rate_limit_retries_honour_retry_after_then_succeed():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")
        return httpx.Response(200, json=OPENAI_OK)

    provider, sleeps = make(GroqProvider, handler)
    out = await provider.generate(REQ, "m")
    assert out.text and calls["n"] == 3 and sleeps == [2.0, 2.0]


async def test_retry_after_is_capped():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "9999"}) if calls["n"] == 1 else httpx.Response(200, json=OPENAI_OK)

    provider, sleeps = make(GroqProvider, handler)
    await provider.generate(REQ, "m")
    assert sleeps == [5]


async def test_retries_exhausted_raises_rate_limit():
    provider, sleeps = make(GroqProvider, lambda r: httpx.Response(429, text="no"), retries=2)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.RATE_LIMIT and exc.value.retryable and len(sleeps) == 2


async def test_server_error_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, text="down") if calls["n"] == 1 else httpx.Response(200, json=OPENAI_OK)

    provider, _ = make(DeepSeekProvider, handler)
    assert (await provider.generate(REQ, "m")).text and calls["n"] == 2


@pytest.mark.parametrize("status,kind", [(401, ProviderErrorKind.AUTH), (403, ProviderErrorKind.AUTH),
                                         (400, ProviderErrorKind.BAD_REQUEST), (404, ProviderErrorKind.BAD_REQUEST)])
async def test_client_errors_not_retried(status, kind):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(status, text="nope")

    provider, sleeps = make(GroqProvider, handler)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == kind and calls["n"] == 1 and sleeps == []


async def test_timeout_and_network_errors_mapped_and_retried():
    def timeout_handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    provider, sleeps = make(GroqProvider, timeout_handler, retries=1)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.TIMEOUT and len(sleeps) == 1

    def network_handler(request):
        raise httpx.ConnectError("refused", request=request)

    provider, _ = make(GroqProvider, network_handler, retries=0)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.NETWORK


async def test_error_messages_never_leak_the_key():
    # Providers sometimes echo the credential in error bodies.
    provider, _ = make(GroqProvider, lambda r: httpx.Response(400, text=f"Invalid key {KEY} supplied"))
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert KEY not in str(exc.value) and KEY not in exc.value.message


async def test_missing_key_or_model_fails_without_network_call():
    def handler(request):
        raise AssertionError("network must not be called")

    provider, _ = make(GroqProvider, handler, key=None)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "m")
    assert exc.value.kind == ProviderErrorKind.NOT_CONFIGURED

    provider, _ = make(GroqProvider, handler)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(REQ, "")
    assert exc.value.kind == ProviderErrorKind.NOT_CONFIGURED


# ----------------------------------------------------------------- factory
def test_factory_builds_each_provider_from_settings():
    s = make_settings(deepseek_api_key="k1-aaaaaaaaaa", groq_api_key="k2-aaaaaaaaaa",
                      gemini_api_key="k3-aaaaaaaaaa",
                      llm_timeout_seconds=12, llm_max_retries=4)
    assert set(PROVIDER_CLASSES) == {"deepseek", "groq", "gemini"}
    for name, cls in PROVIDER_CLASSES.items():
        p = build_provider(name, s)
        assert isinstance(p, cls) and p.timeout == 12 and p.max_retries == 4
    assert build_provider("groq", s).base_url == "https://api.groq.com/openai/v1"
    assert build_provider("deepseek", s).base_url == "https://api.deepseek.com"
    with pytest.raises(ValueError):
        build_provider("skynet", s)


async def test_gemini_ignores_thought_parts():
    payload = {"candidates": [{"content": {"parts": [{"text": "reasoning...", "thought": True}, {"text": '{"ok": true}'}]}}]}
    provider, _ = make(GeminiProvider, lambda r: httpx.Response(200, json=payload))
    out = await provider.generate(REQ, "m")
    assert out.text == '{"ok": true}'
