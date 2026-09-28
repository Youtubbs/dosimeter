"""Tests for the deterministic evaluate_rule tool adapter."""

import pytest
from pydantic import ValidationError

from dosimeter.domain.rules import RuleInvocation
from dosimeter.tools.base import Tool

from dosimeter.tools.rules import (
    EVALUATE_RULE,
    EVALUATE_RULE_TOOL,
    EvaluateRuleRequest,
    evaluate_rule,
    rule_tools,
)


def test_evaluate_r1_records_tool_invocation() -> None:
    invocation = evaluate_rule(
        {
            "rule_id": "R1",
            "inputs": {
                "tede": {
                    "value": 25.0,
                    "unit": "rem",
                },
                "lens": None,
                "shallow": None,
                "intake": None,
            },
        }
    )

    assert isinstance(invocation, RuleInvocation)
    assert invocation.rule_id == "R1"
    assert invocation.path == "tool"
    assert invocation.result.rule_id == "R1"


def test_evaluate_r2_records_tool_invocation() -> None:
    invocation = evaluate_rule(
        {
            "rule_id": "R2",
            "inputs": {
                "loss_of_control": True,
                "tede": {
                    "value": 5.01,
                    "unit": "rem",
                },
                "lens": None,
                "shallow": None,
                "intake": None,
            },
        }
    )

    assert invocation.rule_id == "R2"
    assert invocation.path == "tool"
    assert invocation.result.rule_id == "R2"


def test_r1_rejects_unknown_input() -> None:
    with pytest.raises(ValueError):
        evaluate_rule(
            {
                "rule_id": "R1",
                "inputs": {
                    "made_up_dose": {
                        "value": 25.0,
                        "unit": "rem",
                    },
                },
            }
        )


def test_r2_rejects_non_boolean_loss_of_control() -> None:
    with pytest.raises(TypeError):
        evaluate_rule(
            {
                "rule_id": "R2",
                "inputs": {
                    "loss_of_control": "yes",
                },
            }
        )


def test_invalid_rule_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluateRuleRequest.model_validate(
            {
                "rule_id": "R99",
                "inputs": {},
            }
        )


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvaluateRuleRequest.model_validate(
            {
                "rule_id": "R1",
                "inputs": {},
                "threshold": 25,
            }
        )


def test_evaluate_rule_converts_json_unit_to_domain_enum() -> None:
    invocation = evaluate_rule(
        {
            "rule_id": "R1",
            "inputs": {
                "tede": {
                    "value": 25.0,
                    "unit": "rem",
                },
                "lens": None,
                "shallow": None,
                "intake": None,
            },
        }
    )

    assert invocation.result.rule_id == "R1"


def test_evaluate_rule_tool_has_expected_contract() -> None:
    tool = EVALUATE_RULE_TOOL

    assert isinstance(tool, Tool)
    assert tool.name == EVALUATE_RULE
    assert tool.input_model is EvaluateRuleRequest
    assert tool.output_model is RuleInvocation


def test_evaluate_rule_tool_does_not_expose_subject() -> None:
    assert EVALUATE_RULE_TOOL.subject_arguments() == []


def test_rule_tools_returns_evaluate_rule() -> None:
    tools = rule_tools()

    assert len(tools) == 1
    assert tools[0] is EVALUATE_RULE_TOOL
    assert tools[0].name == "evaluate_rule"
