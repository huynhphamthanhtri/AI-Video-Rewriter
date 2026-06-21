"""Centralized version constants for the preset + prompt system.

All modules import from here instead of hardcoding version numbers.
Bump a constant here to trigger upgrade warnings across the stack."""

from __future__ import annotations

CURRENT_PRESET_SCHEMA_VERSION: int = 1
CURRENT_PROMPT_TEMPLATE_VERSION: int = 1
CURRENT_JSON_OUTPUT_SCHEMA_VERSION: int = 1
