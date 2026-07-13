"""Memory vault: cross-platform paths, keyword fallback, frontmatter stripping."""

import pytest

from vasco.memory import MemoryManager, _strip_frontmatter


@pytest.fixture
def vault(tmp_path, monkeypatch):
    mm = MemoryManager(vault_path=tmp_path / "vault")
    # Force keyword fallback so tests never download an embedding model.
    monkeypatch.setattr(mm, "_get_model", lambda: None)
    return mm


def test_vault_created_at_custom_path(vault, tmp_path):
    assert (tmp_path / "vault").exists()


def test_remember_writes_markdown(vault):
    path = vault.remember("Coffee preference", "The user likes espresso.", "user_facts")
    content = open(path, encoding="utf-8").read()
    assert content.startswith("---")
    assert "The user likes espresso." in content
    assert "category: user_facts" in content


def test_keyword_recall_finds_memory(vault):
    vault.remember("Coffee preference", "The user likes espresso in the morning.", "user")
    vault.remember("Dog name", "The user's dog is called Biscuit.", "user")
    results = vault.recall("what espresso do I like")
    assert results and "espresso" in results[0]["content"]


def test_recall_strips_frontmatter(vault):
    vault.remember("Fact", "Paris is the capital of France.", "general")
    results = vault.recall("capital of France Paris")
    assert results
    assert not results[0]["content"].startswith("---")
    assert "created:" not in results[0]["content"]


def test_recall_no_match_returns_empty(vault):
    vault.remember("Fact", "Paris is the capital of France.", "general")
    assert vault.recall("quantum chromodynamics flux") == []


def test_filename_sanitization(vault):
    path = vault.remember('Weird: "topic"/name?*', "content here", "general")
    assert '"' not in path.rsplit("/", 1)[-1]
    assert "?" not in path


def test_strip_frontmatter_plain_text_untouched():
    assert _strip_frontmatter("no frontmatter here") == "no frontmatter here"
