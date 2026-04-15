#!/usr/bin/env python
"""Quick validation script for promotion system."""

import sys
from pathlib import Path

# Test imports
try:
    from llm_wiki.daemon.jobs.promotion import PromotionJob
    from llm_wiki.promotion.config import PromotionConfig
    from llm_wiki.promotion.engine import PromotionEngine
    from llm_wiki.promotion.models import PromotionCandidate
    from llm_wiki.promotion.scorer import PromotionScorer

    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test config
try:
    config = PromotionConfig()
    assert config.auto_promote_threshold == 10.0
    assert config.min_cross_domain_refs == 2
    print("✓ PromotionConfig works")
except Exception as e:
    print(f"✗ PromotionConfig failed: {e}")
    sys.exit(1)

# Test models
try:
    candidate = PromotionCandidate(
        page_id="test",
        domain="domain1",
        title="Test",
        cross_domain_references=3,
        total_references=5,
        quality_score=0.8,
        page_age_days=30,
        promotion_score=10.0,
        should_auto_promote=True,
        should_suggest_promote=True,
    )
    data = candidate.to_dict()
    assert data["page_id"] == "test"
    print("✓ PromotionCandidate works")
except Exception as e:
    print(f"✗ PromotionCandidate failed: {e}")
    sys.exit(1)

# Test scoring
try:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        wiki_base = Path(tmpdir) / "wiki"
        wiki_base.mkdir()
        scorer = PromotionScorer(config=config, wiki_base=wiki_base)
        candidates = scorer.score_all_pages()
        assert isinstance(candidates, list)
        print("✓ PromotionScorer works")
except Exception as e:
    print(f"✗ PromotionScorer failed: {e}")
    sys.exit(1)

# Test engine
try:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        wiki_base = Path(tmpdir) / "wiki"
        wiki_base.mkdir()
        engine = PromotionEngine(config=config, wiki_base=wiki_base)
        candidates = engine.find_candidates()
        assert isinstance(candidates, list)
        assert (wiki_base / "shared").exists()
        print("✓ PromotionEngine works")
except Exception as e:
    print(f"✗ PromotionEngine failed: {e}")
    sys.exit(1)

# Test job
try:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        wiki_base = Path(tmpdir) / "wiki"
        wiki_base.mkdir()
        job = PromotionJob(wiki_base=wiki_base, config=config)
        result = job.execute()
        assert "status" in result
        print("✓ PromotionJob works")
except Exception as e:
    print(f"✗ PromotionJob failed: {e}")
    sys.exit(1)

print("\n✅ All validation tests passed!")
