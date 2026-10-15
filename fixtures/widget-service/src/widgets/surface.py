"""Pure decision: is the review surface usable right now?

The decision depends only on already-measured facts and returns a code from a
closed vocabulary, so it can be unit-tested without a live surface.
"""
from __future__ import annotations

REASON_VOCABULARY = frozenset(
    {
        "surface-unreachable",
        "lease-missing",
        "navigation-failed",
        "binding-changed",
        "semantic-ineligible",
        "surface-ready",
    }
)


def decide_surface_state(surface: dict, facts: dict) -> tuple[str, str, str]:
    """Return ``(outcome, reason_code, detail)``."""
    if not facts.get("reachable", False):
        return ("unavailable", "surface-unreachable", "sensor did not reach the surface")
    if not facts.get("lease", False):
        return ("unavailable", "lease-missing", "no lease held")
    if not facts.get("navigated", False):
        return ("unavailable", "navigation-failed", "navigation did not complete")
    if facts.get("binding_changed") is None:
        return ("unavailable", "binding-changed", "freshness was not measured")
    if facts.get("binding_changed"):
        return ("unavailable", "binding-changed", "the bound document changed")
    if facts.get("composer_present", False):
        if facts.get("sign_in_affordance", False):
            return ("unavailable", "semantic-ineligible", "sign-in affordance present")
        return ("available", "surface-ready", "composer is present")
    return ("unavailable", "semantic-ineligible", "no composer present")
