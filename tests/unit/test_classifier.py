"""Tests for content-based domain classifier."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_wiki.ingest.classifier import Classifier, _tokenize


class TestTokenize:
    def test_tokenizes_content(self):
        tokens = _tokenize("Proxmox and k3s are my homelab technologies")
        assert "proxmox" in tokens
        assert "k3s" not in tokens  # too short (< 3 chars)
        assert "and" not in tokens  # stopword
        assert "homelab" in tokens

    def test_filters_stopwords(self):
        tokens = _tokenize("the quick brown fox jumps over the lazy dog")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens
        assert "jumps" in tokens
        assert "lazy" in tokens
        assert "dog" in tokens
        assert "the" not in tokens
        assert "over" not in tokens

    def test_lowers_case(self):
        tokens = _tokenize("HeLlO wOrLd")
        assert "hello" in tokens
        assert "world" in tokens


class TestClassifier:
    @pytest.fixture
    def mock_domains(self):
        from unittest.mock import MagicMock

        domains = []
        for d in [
            ("general", "General", "fallback bucket for unclassified or low-confidence content"),
            ("homelab", "Homelab", "proxmox, k3s, storage, networking, GPUs, services"),
            (
                "home-assistant",
                "Home Assistant",
                "automation, voice assistant, ESP32, local AI, sensors",
            ),
        ]:
            d_cfg = MagicMock()
            d_cfg.id = d[0]
            d_cfg.title = d[1]
            d_cfg.description = d[2]
            domains.append(d_cfg)
        return domains

    def test_explicit_domain_from_metadata(self, mock_domains):
        """Explicit domain in metadata overrides classification."""
        with patch("llm_wiki.config.loader.load_config") as mock_load:
            mock_cfg = MagicMock()
            mock_cfg.domains.domains = mock_domains
            mock_load.return_value = mock_cfg

            clf = Classifier(config_dir=Path("config"))
            result = clf.classify("some random content", {"domain": "homelab"})
            assert result == "homelab"

    def test_invalid_explicit_domain_ignored(self, mock_domains):
        """Invalid explicit domain falls through to classifier."""
        with patch("llm_wiki.config.loader.load_config") as mock_load:
            mock_cfg = MagicMock()
            mock_cfg.domains.domains = mock_domains
            mock_load.return_value = mock_cfg

            clf = Classifier(config_dir=Path("config"))
            result = clf.classify(
                "proxmox cluster setup",
                {"domain": "nonexistent-domain"},
            )
            assert result == "homelab"

    def test_heuristic_homelab_classification(self, mock_domains):
        """Content with homelab keywords should match homelab domain."""
        with patch("llm_wiki.config.loader.load_config") as mock_load:
            mock_cfg = MagicMock()
            mock_cfg.domains.domains = mock_domains
            mock_load.return_value = mock_cfg

            clf = Classifier(config_dir=Path("config"))
            result = clf._classify_with_heuristics(
                "proxmox and k3s are my homelab passions",
                {"title": "Proxmox Cluster Setup"},
            )
            assert result == "homelab"

    def test_heuristic_general_fallback(self, mock_domains):
        """When content has no domain keywords, returns general as fallback."""
        with patch("llm_wiki.config.loader.load_config") as mock_load:
            mock_cfg = MagicMock()
            mock_cfg.domains.domains = mock_domains
            mock_load.return_value = mock_cfg

            clf = Classifier(config_dir=Path("config"))
            result = clf._classify_with_heuristics(
                "bring your own device policy for mobile phones",
                {"title": "BYOD Policy"},
            )
            assert result == "general"
