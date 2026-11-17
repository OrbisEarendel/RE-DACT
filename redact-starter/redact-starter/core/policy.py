"""Reads policy.yaml. Owner: P3."""
import os

import yaml

_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.yaml")


def load_policy(path: str = _POLICY_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["levels"]


def action_for(entity_type: str, level: int, overrides: dict | None = None) -> str:
    """overrides lets the user say e.g. {"LOCATION": "keep"} regardless of level."""
    if overrides and entity_type in overrides:
        return overrides[entity_type]
    return load_policy().get(level, {}).get(entity_type, "keep")
