"""
Governance and Maintenance Workflow

This example demonstrates how to run governance checks and maintain
wiki quality over time.
"""

from pathlib import Path

from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.governance.linter import MetadataLinter
from llm_wiki.governance.quality import QualityScorer
from llm_wiki.governance.staleness import StalenessDetector

# Setup
wiki_base = Path("wiki_system")

# Example 1: Run metadata linter
print("=== Metadata Linting ===")
linter = MetadataLinter(wiki_base=wiki_base)

# Lint all pages across all domains
all_issues = linter.lint_all(wiki_base)

print(f"Found {len(all_issues)} total issues:")

# Group by severity
errors = [i for i in all_issues if i.severity == "error"]
warnings = [i for i in all_issues if i.severity == "warning"]

print(f"  Errors: {len(errors)}")
print(f"  Warnings: {len(warnings)}")

# Show first few errors
if errors:
    print("\nFirst 5 errors:")
    for issue in errors[:5]:
        print(f"  - {issue.page_id}: {issue.message}")

# Example 2: Detect stale content
print("\n\n=== Staleness Detection ===")
staleness = StalenessDetector(wiki_base=wiki_base)

# Analyze all pages with staleness score >= 0.3 (somewhat stale)
stale_reports = staleness.analyze_all(min_score=0.3)

print(f"Found {len(stale_reports)} stale pages:")

# Sort by staleness score (highest first)
sorted_reports = sorted(stale_reports, key=lambda r: r.staleness_score, reverse=True)

for report in sorted_reports[:10]:  # Show top 10 stale pages
    print(f"\n  {report.page_id} (score: {report.staleness_score:.2f})")
    print(f"    Age: {report.age_days} days")
    if report.last_updated_days:
        print(f"    Last updated: {report.last_updated_days} days ago")
    if report.time_sensitive_content:
        print("    Time-sensitive: Yes")
    if report.recommendation:
        print(f"    Recommendation: {report.recommendation}")

# Example 3: Quality scoring
print("\n\n=== Quality Scoring ===")
scorer = QualityScorer(wiki_base=wiki_base)

# Score all pages with quality <= 0.6 (low quality)
quality_reports = scorer.score_all(max_score=0.6)

print(f"Found {len(quality_reports)} low-quality pages:")

# Sort by quality score (lowest first)
sorted_quality = sorted(quality_reports, key=lambda r: r.overall_score)

for report in sorted_quality[:10]:  # Show 10 lowest quality pages
    print(f"\n  {report.page_id} (score: {report.overall_score:.2f})")
    print(f"    Metadata: {report.factors['metadata']:.2f}")
    print(f"    Content: {report.factors['content']:.2f}")
    print(f"    Citations: {report.factors['citations']:.2f}")
    print(f"    Recency: {report.factors['recency']:.2f}")

    if report.issues:
        print(f"    Issues: {', '.join(report.issues)}")

# Example 4: Run full governance check (generates report)
print("\n\n=== Full Governance Check ===")
job = GovernanceJob(wiki_base=wiki_base)
stats = job.execute()

print("Governance check complete!")
print(f"  Total pages: {stats['total_pages']}")
print(f"  Lint issues: {stats['lint_issues']}")
print(f"  Lint errors: {stats['lint_errors']}")
print(f"  Stale pages: {stats['stale_pages']}")
print(f"  Low quality pages: {stats['low_quality_pages']}")
print(f"  Report: {stats['report_path']}")

# Example 5: Read governance report
print("\n\n=== Governance Report ===")
if stats["report_path"] and Path(stats["report_path"]).exists():
    report_content = Path(stats["report_path"]).read_text()
    print("Report preview (first 50 lines):")
    print("-" * 60)
    lines = report_content.split("\n")[:50]
    print("\n".join(lines))
    print("-" * 60)

# Example 6: Fix common issues
print("\n\n=== Fixing Issues ===")
print("Common fixes:")
print("  1. Add missing required fields to frontmatter")
print("  2. Update stale content with current information")
print("  3. Add citations for factual claims")
print("  4. Expand short pages with more content")
print("  5. Add tags and summaries to improve metadata")
print("  6. Remove or archive orphan pages")
print("\nSee governance report for specific recommendations.")
