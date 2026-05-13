"""Tests for Phase 1: contract collection and inventory."""

from pathlib import Path

from ddd_archaeology.models import Confidence, ContractType
from ddd_archaeology.phases.collect import collect_contracts, _score_confidence


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery"


def test_collect_finds_all_contracts():
    contracts = collect_contracts(EXAMPLES_DIR)
    assert len(contracts) == 9  # 6 OpenAPI + 2 AsyncAPI + 1 GraphQL


def test_collect_identifies_openapi():
    contracts = collect_contracts(EXAMPLES_DIR)
    openapi_contracts = [c for c in contracts if c.contract_type == ContractType.OPENAPI]
    assert len(openapi_contracts) == 6


def test_collect_identifies_asyncapi():
    contracts = collect_contracts(EXAMPLES_DIR)
    asyncapi_contracts = [c for c in contracts if c.contract_type == ContractType.ASYNCAPI]
    assert len(asyncapi_contracts) == 2


def test_collect_identifies_graphql():
    contracts = collect_contracts(EXAMPLES_DIR)
    gql_contracts = [c for c in contracts if c.contract_type == ContractType.GRAPHQL]
    assert len(gql_contracts) == 1


def test_openapi_endpoint_count():
    contracts = collect_contracts(EXAMPLES_DIR)
    order = next(c for c in contracts if "Shipment Service" in c.service_name and c.contract_type == ContractType.OPENAPI)
    assert order.endpoint_count == 7


def test_asyncapi_channel_count():
    contracts = collect_contracts(EXAMPLES_DIR)
    order_events = next(c for c in contracts if "Shipment Domain" in c.service_name)
    assert order_events.channel_count == 6


def test_graphql_operation_count():
    contracts = collect_contracts(EXAMPLES_DIR)
    gql = next(c for c in contracts if c.contract_type == ContractType.GRAPHQL)
    assert gql.operation_count > 0


def test_schema_count_positive():
    contracts = collect_contracts(EXAMPLES_DIR)
    for c in contracts:
        assert c.schema_count > 0, f"{c.service_name} has 0 schemas"


def test_confidence_scoring():
    assert _score_confidence(None) == Confidence.UNKNOWN
    assert _score_confidence("invalid") == Confidence.UNKNOWN


def test_all_contracts_have_last_modified():
    contracts = collect_contracts(EXAMPLES_DIR)
    for c in contracts:
        assert c.last_modified is not None, f"{c.service_name} missing last_modified"


def test_all_contracts_have_confidence():
    contracts = collect_contracts(EXAMPLES_DIR)
    for c in contracts:
        assert c.confidence != Confidence.UNKNOWN, f"{c.service_name} has unknown confidence"
