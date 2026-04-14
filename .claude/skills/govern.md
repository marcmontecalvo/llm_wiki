# Wiki Governance Skill

Run governance checks on wiki.

## Usage

```
/govern [--show-report]
```

## Description

Run lint, staleness, and quality checks on wiki pages.

## Implementation

```python
from pathlib import Path
from llm_wiki.daemon.jobs.governance import GovernanceJob

wiki_base = Path("wiki_system")
show_report = args.get("show_report", False)

print("Running governance checks...")

try:
    job = GovernanceJob(wiki_base=wiki_base)
    result = job.execute()

    if result["status"] == "success":
        print("\n✓ Governance check complete:")
        print(f"  - Lint issues: {result['lint_issues']}")
        print(f"    - Errors: {result['lint_errors']}")
        print(f"    - Warnings: {result['lint_warnings']}")
        print(f"  - Stale pages: {result['stale_pages']}")
        print(f"  - Low-quality pages: {result['low_quality_pages']}")
        print(f"\n  Report saved: {result['report_path']}")

        if show_report:
            report_path = Path(result['report_path'])
            if report_path.exists():
                print("\n" + "="*60)
                print(report_path.read_text())
                print("="*60)
    else:
        print(f"\n✗ Governance check failed: {result.get('error')}")

except Exception as e:
    print(f"\n✗ Error: {e}")
```

## Examples

- `/govern` - Run checks, show summary
- `/govern --show-report` - Run checks and display full report
