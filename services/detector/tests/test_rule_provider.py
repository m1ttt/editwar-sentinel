import httpx
import pytest

from editwar_detector.rule_provider import RuleProvider, parse_rules
from editwar_domain import DetectionRule, RuleKind, default_rules

API = "http://api.test"


def provider_with(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RuleProvider(API + "/", client=client)


def api_rule(**overrides):
    rule = DetectionRule(name="Burst", kind=RuleKind.BURST, window_seconds=120, threshold=5)
    data = rule.to_dict()
    data.update(overrides)
    return data


async def test_fetch_success():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[api_rule()])

    provider = provider_with(handler)
    rules = await provider.fetch()
    assert calls == [f"{API}/api/rules"]
    assert [r.name for r in rules] == ["Burst"]
    assert rules[0].kind is RuleKind.BURST
    await provider.aclose()


async def test_extra_fields_from_api_are_ignored():
    provider = provider_with(
        lambda request: httpx.Response(200, json=[api_rule(created_at="2026-11-01T00:00:00Z")])
    )
    rules = await provider.fetch()
    assert rules[0].threshold == 5


async def test_first_error_falls_back_to_defaults():
    provider = provider_with(lambda request: httpx.Response(503))
    rules = await provider.fetch()
    assert [r.id for r in rules] == [r.id for r in default_rules()]


async def test_connection_error_falls_back_to_defaults():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    rules = await provider_with(handler).fetch()
    assert len(rules) == 3


async def test_error_keeps_last_good_rules():
    responses = [
        httpx.Response(200, json=[api_rule(name="First")]),
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"items": []}),
        httpx.Response(200, json=[{"name": "missing fields"}]),
    ]
    provider = provider_with(lambda request: responses.pop(0))
    assert [r.name for r in await provider.fetch()] == ["First"]
    for _ in range(4):
        assert [r.name for r in await provider.fetch()] == ["First"]


async def test_empty_list_is_a_valid_answer():
    provider = provider_with(lambda request: httpx.Response(200, json=[]))
    assert await provider.fetch() == []


def test_parse_rules_rejects_non_list():
    with pytest.raises(ValueError):
        parse_rules({"rules": []})


def test_default_client_is_created():
    provider = RuleProvider("http://localhost:8000", refresh_seconds=5)
    assert provider.url == "http://localhost:8000/api/rules"
    assert provider.refresh_seconds == 5
    assert isinstance(provider.client, httpx.AsyncClient)
