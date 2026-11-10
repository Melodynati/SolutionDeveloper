"""Offline unit tests: python3 -m pytest tests/  (or: python3 tests/test_logic.py)"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scoring import holt_forecast, item_signal, momentum_z, rank  # noqa: E402
from taxonomy import keyword_match  # noqa: E402
import extract  # noqa: E402


def test_item_signal_monotonic():
    assert item_signal("github", 1000) > item_signal("github", 10) > item_signal("github", 0) > 0


def test_holt_detects_uptrend():
    fc, slope = holt_forecast([1, 2, 3, 4, 5, 6, 7])
    assert slope > 0 and fc[-1] > 7


def test_holt_never_negative():
    fc, _ = holt_forecast([10, 8, 6, 4, 2, 0, 0])
    assert min(fc) >= 0


def test_momentum_spike():
    assert momentum_z([2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 12]) > 2
    assert momentum_z([5] * 14) == 0


def test_rank_stages():
    flat = [10.0] * 14
    spike_big = [20.0] * 13 + [80.0]
    spike_small = [0.5] * 13 + [6.0]
    cooling = [30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 8, 6, 2]
    rows = rank({"Big": spike_big, "Small": spike_small, "Flat": flat, "Cool": cooling},
                {"Big": {"github", "hackernews", "arxiv"}, "Small": {"arxiv"}, "Flat": {"github"}, "Cool": {"github"}})
    st = {r["tech"]: r["stage"] for r in rows}
    assert st["Big"] == "Breakout"
    assert st["Small"] == "Emerging"          # pioneer signal: small but accelerating
    assert st["Cool"] == "Cooling"
    assert rows[0]["tech"] == "Big"
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]


def test_keyword_fallback():
    hits = keyword_match("Show HN: an open-source MCP server for Postgres with RAG")
    assert "Model Context Protocol (MCP)" in hits and "Retrieval-Augmented Generation (RAG)" in hits


def test_extract_validates_model_output():
    """Model output naming a non-allowed tech must be dropped; new names are cleaned."""
    def fake_converse(**kw):
        return {"usage": {"inputTokens": 100, "outputTokens": 20},
                "output": {"message": {"content": [{"toolUse": {"input": {"results": [
                    {"i": 0, "technologies": ["AI Agents", "Totally Made Up"], "new_technologies": ["test-time training"]},
                    {"i": 7, "technologies": ["AI Agents"]},  # out of range -> ignored
                ]}}}]}}}
    extract._bedrock = lambda: types.SimpleNamespace(converse=fake_converse)
    items = [{"source": "hackernews", "text": "agents"}, {"source": "arxiv", "text": "nothing"}]
    out, stats = extract.extract(items, use_bedrock=True)
    assert out[0]["techs"] == ["AI Agents"]
    assert out[0]["new_techs"] == ["Test-time training"]
    assert out[1]["techs"] == []
    assert stats["input_tokens"] == 100


def test_extract_falls_back_on_error():
    def boom(**kw):
        raise RuntimeError("throttled")
    extract._bedrock = lambda: types.SimpleNamespace(converse=boom)
    out, stats = extract.extract([{"source": "github", "text": "a new vector database"}], use_bedrock=True)
    assert out[0]["techs"] == ["Vector Databases"] and stats["fallback_batches"] == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
