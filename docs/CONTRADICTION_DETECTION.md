# Contradiction Detection

## Overview

The contradiction detector identifies conflicting claims across wiki pages to maintain knowledge consistency. It uses multiple detection strategies to find contradictory statements at varying confidence levels.

## Features

### 1. Multiple Detection Methods

#### Negation Detection
- Identifies explicit negation contradictions
- Examples:
  - "X is supported" vs "X is not supported"
  - "Feature Y is available" vs "Feature Y cannot be used"
- Pattern matching for negation words: "not", "no", "don't", "doesn't", "cannot", "can't", etc.
- Confidence: 0.7-0.95

#### Numerical Contradictions
- Detects claims with different numerical values
- Examples:
  - "Released in 2020" vs "Released in 2019"
  - "Has 5 features" vs "Has 10 features"
- Requires similar claim structure with different numbers
- Confidence: 0.6-0.85

#### Semantic Contradictions
- Uses LLM analysis for complex contradictions
- Checks if claims are semantically opposed
- Considers temporal context and scope
- Confidence: varies based on LLM assessment

### 2. Confidence Scoring

Each contradiction is scored 0.0-1.0:
- **High Confidence (0.8+)**: Strong indicators of contradiction
  - Direct negation pairs
  - Clear numerical differences
  - LLM-confirmed opposition

- **Medium Confidence (0.65-0.79)**: Likely contradictions
  - Similar claims with different values
  - Semantic opposition with qualifications

- **Low Confidence (<0.65)**: Possible contradictions
  - Ambiguous cases
  - May be resolvable with context

### 3. Severity Levels

Contradictions are classified by severity:
- **High**: Strong evidence of contradiction, high confidence
- **Medium**: Moderate evidence or moderate confidence
- **Low**: Weak evidence or low confidence

## Usage

### Command Line

#### Run All Governance Checks with Contradictions
```bash
llm-wiki govern check --wiki-base wiki_system --with-contradictions
```

#### Run Contradiction Detection Separately
```bash
llm-wiki govern contradictions \
    --wiki-base wiki_system \
    --min-confidence 0.6 \
    --output wiki_system/reports/contradictions.md
```

Options:
- `--wiki-base`: Base wiki directory (default: `wiki_system`)
- `--min-confidence`: Minimum confidence threshold (default: `0.6`)
- `--output`: Custom output file path (default: auto-generated in reports/)

### Python API

```python
from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.models.client import ModelClient

# Initialize detector
client = ModelClient()
detector = ContradictionDetector(
    client=client,
    min_similarity_threshold=0.7,
    min_confidence=0.6
)

# Analyze all pages
report = detector.analyze_all_pages(Path("wiki_system"))

# Generate markdown report
detector.generate_report(report, Path("report.md"))

# Access results
print(f"Total: {report.total_contradictions}")
print(f"High confidence: {len(report.high_confidence)}")
print(f"Medium confidence: {len(report.medium_confidence)}")
print(f"Low confidence: {len(report.low_confidence)}")

# By type
for contradiction_type, contradictions in report.by_type.items():
    print(f"{contradiction_type}: {len(contradictions)}")
```

## Detecting Contradictions on Specific Claims

```python
from llm_wiki.models.extraction import ClaimExtraction

# Create claims
claim_1 = ClaimExtraction(
    claim="Python was released in 1991",
    confidence=0.95,
    source_reference="section 1"
)

claim_2 = ClaimExtraction(
    claim="Python was released in 1990",
    confidence=0.85,
    source_reference="section 2"
)

# Check for contradictions
contradiction = detector._check_contradiction_pair(
    claim_1, "page1", claim_2, "page2"
)

if contradiction:
    print(f"Found: {contradiction.explanation}")
    print(f"Confidence: {contradiction.confidence}")
    print(f"Type: {contradiction.contradiction_type}")
```

## Integration with Governance Job

The contradiction detector is integrated into the governance job:

```python
from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.models.client import ModelClient

client = ModelClient()
job = GovernanceJob(client=client)
stats = job.execute()

print(f"Contradictions found: {stats['contradictions']}")
```

## Output Format

### JSON Contradiction Format
```python
contradiction.to_dict()
# Returns:
{
    "claim_1": "Python was released in 1991",
    "page_id_1": "python-page",
    "claim_2": "Python was released in 1990",
    "page_id_2": "python-history-page",
    "type": "numerical",
    "confidence": 0.85,
    "severity": "medium",
    "explanation": "Different release years...",
    "suggested_resolution": "Verify source data..."
}
```

### Markdown Report Format
```markdown
# Contradiction Detection Report

## Summary
- Total contradictions detected: 5
- High confidence: 2
- Medium confidence: 2
- Low confidence: 1

## High Confidence Contradictions

**Claim 1** (python-page): Python was released in 1991
**Claim 2** (python-history-page): Python was released in 1990

**Type**: numerical
**Confidence**: 0.85
**Severity**: medium
**Explanation**: Numerical contradiction...
**Suggested Resolution**: Verify source data...

## Contradictions by Type

### Numerical (3)
...

### Negation (2)
...
```

## Configuration

Configure contradiction detection in governance config:

```yaml
governance:
  contradictions:
    enabled: true
    min_similarity_threshold: 0.7
    min_contradiction_confidence: 0.6
    detection_interval: 86400  # daily
    auto_resolve: false
    add_to_review_queue: true
```

## Performance Considerations

### Claim Extraction
- Extracts up to 20 claims per page (configurable)
- Uses LLM for extraction - impact depends on page count

### Contradiction Detection
- Compares all claim pairs across different pages
- With N claims, compares N*(N-1)/2 pairs
- Negation detection: O(N²) with regex patterns
- Numerical detection: O(N²) with regex patterns
- Semantic detection: O(N²) with LLM calls (can be slow)

### Optimization Tips
1. Limit claims extracted per page
2. Use min_confidence threshold to filter early results
3. Run contradiction detection separately from other checks
4. Consider running on a subset of pages first

## Handling Results

### High Confidence Contradictions
- Should be reviewed immediately
- Suggest determining which source is authoritative
- Consider updating or deprecating less reliable claims

### Medium Confidence Contradictions
- Review for context
- Check temporal applicability
- May be resolvable with additional qualifiers

### Low Confidence Contradictions
- Low priority for human review
- Useful for finding potential issues
- May have high false positive rate

## Temporal Context

Contradictions are often resolved by temporal context:

```python
claim_1 = ClaimExtraction(
    claim="Python 3.10 is the latest version",
    temporal_context="as of 2021"
)

claim_2 = ClaimExtraction(
    claim="Python 3.12 is the latest version",
    temporal_context="as of 2023"
)

# These are NOT contradictions - temporal context resolves them
```

The detector preserves temporal context for human review.

## Testing

### Unit Tests
```bash
python -m pytest tests/unit/test_contradictions.py -v
```

Tests cover:
- Negation detection
- Numerical contradiction detection
- Semantic contradiction detection
- Confidence scoring
- Severity calculation
- Text similarity
- Report generation

### Integration Tests
```bash
python -m pytest tests/integration/test_contradictions_integration.py -v
```

Tests cover:
- Analyzing multiple pages with real wiki structure
- Handling invalid pages gracefully
- Performance with large claim sets
- Report generation with various contradiction types

## Implementation Details

### Architecture

```
ContradictionDetector
├── ClaimsExtractor (extracts claims from pages)
├── Negation Detector (pattern-based)
├── Numerical Detector (pattern-based)
├── Semantic Detector (LLM-based)
└── Report Generator (markdown output)
```

### Key Methods

- `analyze_all_pages()`: Scan all wiki pages for claims and contradictions
- `detect_contradictions()`: Compare claim pairs for contradictions
- `_check_contradiction_pair()`: Analyze one claim pair for contradictions
- `generate_report()`: Create markdown report with results

### Dependencies

- `llm_wiki.extraction.claims.ClaimsExtractor`: For claim extraction
- `llm_wiki.models.client.ModelClient`: For LLM-based semantic analysis
- `llm_wiki.utils.frontmatter.parse_frontmatter`: For parsing page metadata

## Limitations

1. **False Positives**: Semantic analysis may flag non-contradictory claims
2. **False Negatives**: Subtle contradictions may be missed
3. **Context Sensitivity**: May not understand complex contexts or qualifications
4. **Performance**: Semantic analysis with LLM can be slow for large wikis
5. **Temporal Awareness**: Basic temporal context handling, not full timeline analysis

## Future Improvements

1. Machine learning-based contradiction scoring
2. Better handling of temporal contradictions
3. Caching of embedding vectors for faster comparison
4. Automatic resolution suggestions based on source credibility
5. Integration with claims review queue
6. Contradiction clustering and grouping
7. Bidirectional relationship analysis

## Troubleshooting

### No Contradictions Found
- Check that claims are being extracted
- Verify min_confidence threshold isn't too high
- Look at extracted claims in debug logs

### Too Many False Positives
- Increase min_confidence threshold
- Increase min_similarity_threshold
- Disable semantic detection if not needed

### Performance Issues
- Reduce number of claims extracted per page
- Filter by domain before analysis
- Run on subset of pages for testing

### LLM Errors
- Ensure ModelClient is properly configured
- Check API credentials and limits
- Review LLM response format

## Related Features

- **Claims Extraction** (#66): Extracts factual claims from pages
- **Quality Scoring**: Evaluates page quality
- **Staleness Detection**: Finds outdated pages
- **Linting**: Validates page metadata
- **Governance Job**: Orchestrates all governance checks

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [GOVERNANCE.md](GOVERNANCE.md) - Governance framework
- [CLAIMS_EXTRACTION.md](CLAIMS_EXTRACTION.md) - Claims extraction details
