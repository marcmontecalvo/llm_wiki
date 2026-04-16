"""Unit tests for routing mistake detection."""

import pytest

from llm_wiki.governance.routing_mistakes import (
    RoutingMistake,
    RoutingMistakeDetector,
    RoutingMistakeReport,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_detector(**kwargs) -> RoutingMistakeDetector:
    return RoutingMistakeDetector(min_confidence=0.1, **kwargs)


# ---------------------------------------------------------------------------
# RoutingMistake dataclass
# ---------------------------------------------------------------------------


class TestRoutingMistake:
    def test_to_dict_contains_required_keys(self):
        m = RoutingMistake(
            page_id="p1",
            current_domain="general",
            suggested_domain="homelab",
            confidence=0.8,
            reasons=["tag match"],
        )
        d = m.to_dict()
        assert d["page_id"] == "p1"
        assert d["current_domain"] == "general"
        assert d["suggested_domain"] == "homelab"
        assert d["confidence"] == 0.8
        assert d["reasons"] == ["tag match"]
        assert d["status"] == "pending"

    def test_detected_at_is_set_automatically(self):
        m = RoutingMistake(
            page_id="p1",
            current_domain="general",
            suggested_domain="homelab",
            confidence=0.5,
        )
        assert m.detected_at != ""
        # Should be a valid ISO-format timestamp
        assert "T" in m.detected_at

    def test_default_status_is_pending(self):
        m = RoutingMistake(
            page_id="p",
            current_domain="a",
            suggested_domain="b",
            confidence=0.5,
        )
        assert m.status == "pending"


# ---------------------------------------------------------------------------
# _score_tags
# ---------------------------------------------------------------------------


class TestScoreTags:
    def test_returns_empty_when_no_tags(self):
        d = make_detector()
        assert d._score_tags([], "general") == {}

    def test_returns_empty_when_current_domain_only_match(self):
        d = make_detector()
        # "proxmox" is a homelab keyword — if current domain IS homelab, no foreign score
        scores = d._score_tags(["proxmox"], "homelab")
        assert "homelab" not in scores

    def test_detects_homelab_keywords_from_general(self):
        d = make_detector()
        scores = d._score_tags(["proxmox", "k3s", "docker"], "general")
        assert "homelab" in scores
        assert scores["homelab"] > 0

    def test_score_proportional_to_overlap(self):
        d = make_detector()
        # 2 out of 4 tags match homelab
        scores_two = d._score_tags(["proxmox", "k3s", "cooking", "reading"], "general")
        # 1 out of 4 tags match homelab
        scores_one = d._score_tags(["proxmox", "cooking", "reading", "writing"], "general")
        assert scores_two.get("homelab", 0) > scores_one.get("homelab", 0)

    def test_case_insensitive_matching(self):
        d = make_detector()
        scores = d._score_tags(["PROXMOX", "K3S"], "general")
        assert "homelab" in scores


# ---------------------------------------------------------------------------
# _score_link_affinity
# ---------------------------------------------------------------------------


class TestScoreLinkAffinity:
    def test_returns_none_when_no_links(self):
        d = make_detector()
        assert d._score_link_affinity("no links here", "general", {}) is None

    def test_returns_none_when_fewer_than_two_resolvable(self):
        d = make_detector()
        body = "[[page-a]]"
        page_map = {"page-a": "homelab"}
        assert d._score_link_affinity(body, "general", page_map) is None

    def test_returns_none_when_all_links_in_current_domain(self):
        d = make_detector()
        body = "[[page-a]] [[page-b]] [[page-c]]"
        page_map = {"page-a": "homelab", "page-b": "homelab", "page-c": "homelab"}
        # Current domain IS homelab → no foreign affinity
        result = d._score_link_affinity(body, "homelab", page_map)
        assert result is None

    def test_detects_clear_foreign_majority(self):
        d = make_detector()
        body = "[[p1]] [[p2]] [[p3]] [[p4]]"
        page_map = {"p1": "homelab", "p2": "homelab", "p3": "homelab", "p4": "general"}
        result = d._score_link_affinity(body, "general", page_map)
        assert result is not None
        domain, ratio = result
        assert domain == "homelab"
        assert ratio == pytest.approx(0.75)

    def test_ignores_links_not_in_map(self):
        d = make_detector()
        body = "[[known-a]] [[known-b]] [[unknown]]"
        page_map = {"known-a": "homelab", "known-b": "homelab"}
        # Only 2 resolvable links, both in homelab but current is general
        result = d._score_link_affinity(body, "general", page_map)
        assert result is not None
        domain, ratio = result
        assert domain == "homelab"
        assert ratio == pytest.approx(1.0)

    def test_returns_none_when_no_clear_majority(self):
        d = make_detector()
        # 50% homelab, 50% personal → below 60% threshold
        body = "[[p1]] [[p2]] [[p3]] [[p4]]"
        page_map = {"p1": "homelab", "p2": "homelab", "p3": "personal", "p4": "personal"}
        result = d._score_link_affinity(body, "general", page_map)
        assert result is None


# ---------------------------------------------------------------------------
# _analyze_page
# ---------------------------------------------------------------------------


class TestAnalyzePage:
    def test_no_mistake_when_no_signal(self):
        d = make_detector()
        result = d._analyze_page(
            "page1",
            "general",
            {"tags": []},
            "some content",
            {},
        )
        assert result is None

    def test_explicit_domain_mismatch(self):
        d = make_detector()
        result = d._analyze_page(
            "page1",
            "general",
            {"domain": "homelab"},
            "some content",
            {},
        )
        assert result is not None
        assert result.suggested_domain == "homelab"
        assert result.confidence >= 0.7
        assert any("homelab" in r for r in result.reasons)

    def test_tag_based_detection(self):
        d = make_detector()
        result = d._analyze_page(
            "page1",
            "general",
            {"tags": ["proxmox", "k3s", "kubernetes"]},
            "content",
            {},
        )
        assert result is not None
        assert result.suggested_domain == "homelab"

    def test_returns_none_below_min_confidence(self):
        d = RoutingMistakeDetector(min_confidence=0.9)
        # Single weak tag signal
        result = d._analyze_page(
            "page1",
            "general",
            {"tags": ["proxmox"]},
            "content",
            {},
        )
        # proxmox alone: 1/1 tag overlap * 0.5 weight = 0.5 < 0.9
        assert result is None

    def test_current_domain_not_suggested(self):
        d = make_detector()
        # Tags match homelab; page IS in homelab → should not flag
        result = d._analyze_page(
            "page1",
            "homelab",
            {"tags": ["proxmox", "k3s"]},
            "content",
            {},
        )
        assert result is None

    def test_link_affinity_contributes(self):
        d = make_detector()
        page_map = {
            "ha-page": "home-assistant",
            "ha-page2": "home-assistant",
            "ha-page3": "home-assistant",
        }
        result = d._analyze_page(
            "page1",
            "general",
            {"tags": []},
            "[[ha-page]] [[ha-page2]] [[ha-page3]]",
            page_map,
        )
        assert result is not None
        assert result.suggested_domain == "home-assistant"

    def test_combined_signal_increases_confidence(self):
        d = make_detector()
        page_map = {
            "ha-page": "home-assistant",
            "ha-page2": "home-assistant",
            "ha-page3": "home-assistant",
        }
        # Tag signal + link affinity both pointing at home-assistant
        result_both = d._analyze_page(
            "page1",
            "general",
            {"tags": ["automation", "sensor"]},
            "[[ha-page]] [[ha-page2]] [[ha-page3]]",
            page_map,
        )
        result_tags_only = d._analyze_page(
            "page1",
            "general",
            {"tags": ["automation", "sensor"]},
            "no links",
            {},
        )
        assert result_both is not None
        assert result_tags_only is not None
        assert result_both.confidence >= result_tags_only.confidence


# ---------------------------------------------------------------------------
# analyze_all_pages (filesystem integration)
# ---------------------------------------------------------------------------


class TestAnalyzeAllPages:
    def test_empty_domains_dir(self, tmp_path):
        (tmp_path / "domains").mkdir()
        d = RoutingMistakeDetector(min_confidence=0.1)
        report = d.analyze_all_pages(tmp_path)
        assert report.total_pages_scanned == 0
        assert report.total_mistakes == 0

    def test_missing_domains_dir(self, tmp_path):
        d = RoutingMistakeDetector(min_confidence=0.1)
        report = d.analyze_all_pages(tmp_path)
        assert report.total_pages_scanned == 0
        assert report.total_mistakes == 0

    def test_detects_frontmatter_mismatch(self, tmp_path):
        pages_dir = tmp_path / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)
        page = pages_dir / "my-page.md"
        page.write_text(
            "---\nid: my-page\ndomain: homelab\n---\n\nsome homelab stuff",
            encoding="utf-8",
        )
        d = RoutingMistakeDetector(min_confidence=0.1)
        report = d.analyze_all_pages(tmp_path)
        assert report.total_pages_scanned == 1
        assert report.total_mistakes == 1
        assert report.high_confidence[0].suggested_domain == "homelab"

    def test_no_mistake_for_correct_page(self, tmp_path):
        pages_dir = tmp_path / "domains" / "homelab" / "pages"
        pages_dir.mkdir(parents=True)
        page = pages_dir / "my-page.md"
        page.write_text(
            "---\nid: my-page\ntags: [proxmox, k3s]\n---\n\nproxmox setup",
            encoding="utf-8",
        )
        d = RoutingMistakeDetector(min_confidence=0.1)
        report = d.analyze_all_pages(tmp_path)
        assert report.total_pages_scanned == 1
        assert report.total_mistakes == 0

    def test_confidence_tiers(self, tmp_path):
        # High confidence: explicit mismatch
        high_dir = tmp_path / "domains" / "general" / "pages"
        high_dir.mkdir(parents=True)
        (high_dir / "high.md").write_text(
            "---\nid: high\ndomain: homelab\n---\ncontent", encoding="utf-8"
        )
        # Low confidence: single tag match
        low_dir = tmp_path / "domains" / "personal" / "pages"
        low_dir.mkdir(parents=True)
        (low_dir / "low.md").write_text(
            "---\nid: low\ntags: [proxmox]\n---\ncontent", encoding="utf-8"
        )
        d = RoutingMistakeDetector(min_confidence=0.1)
        report = d.analyze_all_pages(tmp_path)
        assert len(report.high_confidence) >= 1
        # Check the explicit mismatch is high confidence
        high_page = next((m for m in report.high_confidence if m.page_id == "high"), None)
        assert high_page is not None
        assert high_page.confidence >= 0.7


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_creates_file(self, tmp_path):
        d = make_detector()
        report = RoutingMistakeReport(
            total_pages_scanned=10,
            total_mistakes=2,
            high_confidence=[
                RoutingMistake(
                    page_id="p1",
                    current_domain="general",
                    suggested_domain="homelab",
                    confidence=0.9,
                    reasons=["tag match"],
                )
            ],
        )
        out = tmp_path / "report.md"
        result = d.generate_report(report, out)
        assert result == out
        assert out.exists()
        text = out.read_text()
        assert "Routing Mistake Detection Report" in text
        assert "p1" in text
        assert "homelab" in text

    def test_creates_parent_dirs(self, tmp_path):
        d = make_detector()
        report = RoutingMistakeReport(total_pages_scanned=0, total_mistakes=0)
        out = tmp_path / "nested" / "dir" / "report.md"
        d.generate_report(report, out)
        assert out.exists()

    def test_summary_counts_are_correct(self, tmp_path):
        d = make_detector()
        mistakes = [
            RoutingMistake("a", "general", "homelab", 0.8, reasons=[]),
            RoutingMistake("b", "general", "personal", 0.5, reasons=[]),
            RoutingMistake("c", "general", "homelab", 0.35, reasons=[]),
        ]
        report = RoutingMistakeReport(
            total_pages_scanned=20,
            total_mistakes=3,
            high_confidence=[mistakes[0]],
            medium_confidence=[mistakes[1]],
            low_confidence=[mistakes[2]],
        )
        out = tmp_path / "r.md"
        d.generate_report(report, out)
        text = out.read_text()
        assert "Pages scanned: 20" in text
        assert "Total potential mistakes: 3" in text
        assert "High confidence" in text
        assert "Medium confidence" in text
        assert "Low confidence" in text
