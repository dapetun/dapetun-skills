"""Tests for stdlib YAML subset loader."""

from __future__ import annotations

import pytest

from skill_optimizer.simple_yaml import SimpleYAMLError, loads


def test_mapping_and_list():
    doc = loads(
        """
platforms:
  - cursor
  - agents
thresholds:
  body_jaccard_overlap: 0.85
  exact_duplicate_hash: true
"""
    )
    assert doc["platforms"] == ["cursor", "agents"]
    assert doc["thresholds"]["body_jaccard_overlap"] == 0.85
    assert doc["thresholds"]["exact_duplicate_hash"] is True


def test_unclosed_flow_raises():
    with pytest.raises(SimpleYAMLError):
        loads("description: [unclosed\n")


def test_quoted_string():
    assert loads('description: "hello world"\n')["description"] == "hello world"
