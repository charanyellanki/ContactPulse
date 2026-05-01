"""Eval harness — labeled test set, runner, error analysis.

The eval harness measures the agent pipeline against a held-out, hand-curated
test set. It is the primary deliverable per SPEC.md: "the eval harness is the
hero." Production code paths never import from here (CLAUDE.md §4).
"""
