# Contradiction Detector - Quick Start Guide

## Overview
Detects conflicting claims across wiki pages using negation, numerical, and semantic analysis.

## Installation
No additional dependencies required. Already integrated into the project.

## Basic Usage

### Command Line
```bash
# Detect contradictions
llm-wiki govern contradictions --wiki-base wiki_system

# High confidence only
llm-wiki govern contradictions --wiki-base wiki_system --min-confidence 0.8

# Custom output
llm-wiki govern contradictions --wiki-base wiki_system --output report.md
```

### Python API
```python
from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.models.client import ModelClient
from pathlib import Path

# Initialize
client = ModelClient()
detector = ContradictionDetector(client=client, min_confidence=0.6)

# Analyze
report = detector.analyze_all_pages(Path("wiki_system"))

# Generate report
detector.generate_report(report, Path("contradictions.md"))

# Check results
print(f"Found {report.total_contradictions} contradictions")
print(f"  High confidence: {len(report.high_confidence)}")
print(f"  Medium confidence: {len(report.medium_confidence)}")
print(f"  Low confidence: {len(report.low_confidence)}")
```

## Detection Methods

### Negation Detection
Finds: "X is Y" vs "X is not Y"
- Confidence: 0.7-0.95
- Uses pattern matching + word overlap
- High precision

### Numerical Detection
Finds: "Released in 2020" vs "Released in 2019"
- Confidence: 0.6-0.85
- Uses regex-based value comparison
- High precision

### Semantic Detection
Finds: Complex contradictions via LLM analysis
- Confidence: varies
- Uses LLM for analysis
- Good for complex cases

## Configuration

```python
# Initialize with custom settings
detector = ContradictionDetector(
    client=client,
    min_similarity_threshold=0.75,  # For negation confirmation
    min_confidence=0.7              # Minimum to report
)
```

## Output Format

### Report Object
```python
report = detector.analyze_all_pages(wiki_base)

# Access contradictions
report.high_confidence        # List of high confidence
report.medium_confidence      # List of medium confidence
report.low_confidence         # List of low confidence
report.by_type               # Dict grouped by type
report.total_contradictions  # Total count
report.timestamp             # When report was generated
```

### Contradiction Object
```python
contradiction = report.high_confidence[0]

contradiction.claim_1              # First ClaimExtraction
contradiction.claim_2              # Second ClaimExtraction
contradiction.page_id_1            # First page
contradiction.page_id_2            # Second page
contradiction.contradiction_type   # "negation", "numerical", "opposition"
contradiction.confidence           # 0.0-1.0
contradiction.severity             # "low", "medium", "high"
contradiction.explanation          # Why they contradict
contradiction.suggested_resolution # How to resolve
```

## Testing

### Run Tests
```bash
# Unit tests
python -m pytest tests/unit/test_contradictions.py -v

# Integration tests
python -m pytest tests/integration/test_contradictions_integration.py -v

# Both
python -m pytest tests/unit/test_contradictions.py tests/integration/test_contradictions_integration.py -v
```

### Test Coverage
- 20+ unit test cases
- 13+ integration test cases
- All detection methods
- Edge cases
- Error scenarios

## Troubleshooting

### No contradictions found
- Check claims are being extracted
- Lower min_confidence threshold
- Check logs for errors

### Too many results
- Increase min_confidence threshold
- Filter by type in results
- Check for false positives

### Slow performance
- Run on subset of pages first
- Use min_confidence threshold to filter early
- Consider disabling semantic detection

## Integration with Governance

```python
from llm_wiki.daemon.jobs.governance import GovernanceJob

# With contradiction detection
job = GovernanceJob(client=client)
stats = job.execute()

print(f"Contradictions: {stats['contradictions']}")
```

## Files

### Core
- `src/llm_wiki/governance/contradictions.py` - Main implementation

### Tests
- `tests/unit/test_contradictions.py` - Unit tests
- `tests/integration/test_contradictions_integration.py` - Integration tests

### Documentation
- `CONTRADICTION_DETECTION.md` - Full user guide
- `IMPLEMENTATION_SUMMARY.md` - Technical overview
- `IMPLEMENTATION_REPORT.md` - Detailed report

## Common Tasks

### Analyze single page
```python
from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.utils.frontmatter import parse_frontmatter

extractor = ClaimsExtractor(client)

content = page.read_text()
metadata, body = parse_frontmatter(content)
claims = extractor.extract_claims(body, metadata, page_id)
```

### Compare two claims
```python
contradiction = detector._check_contradiction_pair(
    claim_1, page_id_1,
    claim_2, page_id_2
)

if contradiction:
    print(f"Contradiction found: {contradiction.explanation}")
```

### Filter results
```python
# High confidence only
high_only = report.high_confidence

# Specific type
negations = report.by_type.get("negation", [])

# Custom filter
filtered = [c for c in report.high_confidence
            if "Python" in c.claim_1.claim]
```

## Examples

### Example 1: Basic Detection
```python
from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.models.client import ModelClient
from pathlib import Path

detector = ContradictionDetector(client=ModelClient())
report = detector.analyze_all_pages(Path("wiki_system"))

for c in report.high_confidence:
    print(f"{c.page_id_1} vs {c.page_id_2}")
    print(f"  {c.claim_1.claim}")
    print(f"  {c.claim_2.claim}")
    print()
```

### Example 2: Generate Report
```python
report = detector.analyze_all_pages(wiki_base)
detector.generate_report(report, Path("contradictions.md"))

# View report
with open("contradictions.md") as f:
    print(f.read())
```

### Example 3: Governance Integration
```python
from llm_wiki.daemon.jobs.governance import GovernanceJob

job = GovernanceJob(client=ModelClient())
stats = job.execute()

print(f"Contradictions found: {stats['contradictions']}")
print(f"Report: {stats['report_path']}")
```

## Performance Notes

- 50 pages with ~10 claims each: <10 seconds
- Negation/Numerical: <1 second
- Semantic (with LLM): 5-10 seconds
- Memory: ~10MB for typical wiki

## Limits

- Max 20 claims per page extracted
- Processes all page pairs
- LLM-based semantic analysis can be slow
- Temporal context: basic only

## Next Steps

1. Run tests to verify installation
2. Test with your wiki data
3. Review generated reports
4. Configure min_confidence threshold
5. Integrate with workflow

## Support

See `CONTRADICTION_DETECTION.md` for:
- Full feature documentation
- Troubleshooting guide
- Configuration options
- Performance tuning

## Related

- Claims Extraction (#66): Provides claims for comparison
- Governance Framework: Integration point
- Review Queue (#53): Future resolution workflow
