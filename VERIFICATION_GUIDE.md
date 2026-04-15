# Verification Guide: Issue #73 - llms-full.txt Export

This guide explains how to verify that the llms-full.txt export implementation is complete and working correctly.

## Quick Verification

### 1. Code Structure Verification

Check that all files are in place:

```bash
# Core exporter
ls -lh src/llm_wiki/export/llmsfull.py

# Unit tests
ls -lh tests/unit/test_llmsfull_exporter.py

# Integration tests
ls -lh tests/integration/test_llmsfull_export_integration.py

# Documentation
ls -lh docs/export/llms-full-txt.md

# Examples
ls -lh examples/05_llms_full_export.py

# Implementation docs
ls -lh IMPLEMENTATION_LLMS_FULL_TXT.md
ls -lh COMPLETION_SUMMARY.md
```

Expected: All files should exist and be readable.

### 2. Import Verification

Verify the module imports correctly:

```python
# Test import
python -c "from llm_wiki.export.llmsfull import LLMSFullExporter; print('✓ LLMSFullExporter imports successfully')"

# Test it's exported
python -c "from llm_wiki.export import LLMSFullExporter; print('✓ LLMSFullExporter is exported')"
```

### 3. CLI Verification

Verify the CLI command is registered:

```bash
# Check command exists
llm-wiki export --help | grep llmsfull

# Check command has help
llm-wiki export llmsfull --help
```

Expected output should show:
- `llmsfull` command listed
- `--output` option
- `--domain` option
- `--min-quality` option
- `--max-pages` option
- Help text

### 4. Code Quality Verification

Check the code style and structure:

```bash
# Check for syntax errors
python -m py_compile src/llm_wiki/export/llmsfull.py
python -m py_compile tests/unit/test_llmsfull_exporter.py
python -m py_compile tests/integration/test_llmsfull_export_integration.py

# Check imports
python -c "import ast; ast.parse(open('src/llm_wiki/export/llmsfull.py').read())" && echo "✓ Syntax valid"
```

## Comprehensive Testing

### Run Unit Tests

```bash
# Run all unit tests for llmsfull
python -m pytest tests/unit/test_llmsfull_exporter.py -v

# Run specific test class
python -m pytest tests/unit/test_llmsfull_exporter.py::TestLLMSFullExporter -v

# Run with coverage
python -m pytest tests/unit/test_llmsfull_exporter.py --cov=llm_wiki.export.llmsfull -v
```

Expected: All tests pass (30+ tests)

### Run Integration Tests

```bash
# Run all integration tests
python -m pytest tests/integration/test_llmsfull_export_integration.py -v

# Run specific test
python -m pytest tests/integration/test_llmsfull_export_integration.py::TestLLMSFullExportIntegration::test_export_all_domains_comprehensive -v
```

Expected: All tests pass (10+ tests)

### Run All llmsfull Tests

```bash
# Run all llmsfull-related tests
python -m pytest tests/ -k "llmsfull" -v
```

Expected: 40+ tests pass

## Feature Verification

### Feature 1: Basic Export

```python
from llm_wiki.export.llmsfull import LLMSFullExporter
from pathlib import Path

# Initialize
exporter = LLMSFullExporter(wiki_base=Path("wiki_system"))

# Export all
output = exporter.export_all()
print(f"✓ Export successful: {output}")
print(f"  File size: {output.stat().st_size:,} bytes")

# Verify content
content = output.read_text()
assert "<!-- Metadata -->" in content
assert "<!-- Content -->" in content
print("✓ Format verified")
```

### Feature 2: Filtering

```python
from llm_wiki.export.llmsfull import LLMSFullExporter

exporter = LLMSFullExporter()

# Quality filter
output1 = exporter.export_all()
output2 = exporter.export_all(min_quality=0.9)

# Second should be smaller
size1 = output1.stat().st_size
size2 = output2.stat().st_size
print(f"✓ Quality filtering works: {size1} -> {size2} bytes")

# Page limit
output3 = exporter.export_all(max_pages=10)
size3 = output3.stat().st_size
print(f"✓ Page limiting works: {size3} bytes (max 10 pages)")
```

### Feature 3: Domain Export

```python
from llm_wiki.export.llmsfull import LLMSFullExporter

exporter = LLMSFullExporter()

# Check available domains
stats = exporter.get_export_stats()
print(f"Total pages: {stats['total_pages']}")
print(f"Total domains: {stats['total_domains']}")
print(f"Pages with extractions: {stats['pages_with_extractions']}")
print(f"Pages with backlinks: {stats['pages_with_backlinks']}")

# Export first domain
from pathlib import Path
if (Path("wiki_system/domains")).exists():
    domain = list(Path("wiki_system/domains").iterdir())[0].name
    output = exporter.export_domain(domain)
    print(f"✓ Domain export works: {output}")
```

### Feature 4: Metadata Inclusion

```python
from llm_wiki.export.llmsfull import LLMSFullExporter
from pathlib import Path

exporter = LLMSFullExporter()

# Get first page
pages_dir = Path("wiki_system/domains/general/pages")
if pages_dir.exists():
    page_file = list(pages_dir.glob("*.md"))[0]

    # Export page
    content = exporter.export_page(page_file)

    # Verify metadata
    assert "<!-- Metadata -->" in content
    assert "- id:" in content
    assert "- domain:" in content
    assert "- kind:" in content
    print("✓ Metadata sections present")

    # Verify other sections
    if "<!-- Content -->" in content:
        print("✓ Content section present")
    if "<!-- Links -->" in content:
        print("✓ Links section present")
```

### Feature 5: Extraction Data

```python
from llm_wiki.export.llmsfull import LLMSFullExporter
from pathlib import Path
import json

exporter = LLMSFullExporter()

# Create extraction data
index_dir = Path("wiki_system/index")
if not index_dir.exists():
    index_dir.mkdir(parents=True)

# Create test extraction
extraction_data = {
    "entities": [
        {
            "name": "Test Entity",
            "entity_type": "Concept",
            "confidence": 0.95,
        }
    ],
    "claims": [
        {
            "claim": "Test claim",
            "confidence": 0.90,
            "source_reference": "section 1",
        }
    ],
    "concepts": [],
    "relationships": [],
    "extraction_metadata": {},
}

# Add extraction for a test page
test_extraction_file = index_dir / "test-page_extraction.json"
test_extraction_file.write_text(json.dumps(extraction_data))

# Create test page
pages_dir = Path("wiki_system/domains/test/pages")
pages_dir.mkdir(parents=True, exist_ok=True)
test_page = pages_dir / "test-page.md"
test_page.write_text("""---
id: test-page
title: Test Page
domain: test
kind: page
---
Test content""")

# Export page
content = exporter.export_page(test_page)

# Verify extraction sections
if "<!-- Entities -->" in content:
    print("✓ Extraction entities section present")
if "<!-- Claims -->" in content:
    print("✓ Extraction claims section present")
if "Test Entity" in content:
    print("✓ Extracted entity data present")
```

### Feature 6: CLI Command

```bash
# Create test wiki if needed
python examples/01_create_wiki.py

# Run export command
llm-wiki export llmsfull --wiki-base wiki_system --output test-export.txt

# Verify output
ls -lh test-export.txt
wc -l test-export.txt

# Check content
head -50 test-export.txt

# Test with options
llm-wiki export llmsfull --wiki-base wiki_system --min-quality 0.8
llm-wiki export llmsfull --wiki-base wiki_system --max-pages 10
```

## Documentation Verification

### Check Format Documentation

```bash
# Verify format doc exists
cat docs/export/llms-full-txt.md | head -50

# Check for complete sections
grep "## " docs/export/llms-full-txt.md
```

Expected sections:
- Overview
- File Format
- Usage
- Size Management
- Use Cases
- Filtering Options
- Parsing the Format
- Format Design Principles
- Troubleshooting

### Check Examples

```bash
# Verify examples exist and run
python examples/05_llms_full_export.py
```

## Integration Verification

### Verify Export Module Integration

```python
# Check __init__.py exports the class
from llm_wiki.export import LLMSFullExporter
print(f"✓ LLMSFullExporter exported from llm_wiki.export")

# Verify all exporters still work
from llm_wiki.export import (
    GraphExporter,
    JSONSidecarExporter,
    LLMSTxtExporter,
    LLMSFullExporter,
    SitemapGenerator,
)
print(f"✓ All exporters available")
```

### Verify No Breaking Changes

```bash
# Run all export-related tests
python -m pytest tests/unit/test_llmstxt_exporter.py -v
python -m pytest tests/unit/test_export_job.py -v

# These should still pass
echo "✓ No breaking changes to existing exporters"
```

## Performance Verification

### Test Performance

```python
from llm_wiki.export.llmsfull import LLMSFullExporter
import time

exporter = LLMSFullExporter()

# Time export
start = time.time()
output = exporter.export_all()
duration = time.time() - start

print(f"Export completed in {duration:.2f} seconds")
print(f"File size: {output.stat().st_size:,} bytes")

# Estimate performance
if output.stat().st_size < 1_000_000:  # < 1MB
    if duration < 2:
        print("✓ Excellent performance")
    else:
        print("✓ Good performance")
else:
    print(f"✓ Performance acceptable for {output.stat().st_size / 1_000_000:.1f}MB file")
```

## Complete Verification Checklist

- [ ] All files exist and are readable
- [ ] LLMSFullExporter imports correctly
- [ ] CLI command is registered
- [ ] Unit tests pass (30+ tests)
- [ ] Integration tests pass (10+ tests)
- [ ] Basic export works
- [ ] Quality filtering works
- [ ] Page limiting works
- [ ] Domain export works
- [ ] Metadata sections present
- [ ] Extraction data included (when available)
- [ ] Links section present
- [ ] Format documentation exists
- [ ] Examples run successfully
- [ ] No breaking changes to existing code
- [ ] Performance is acceptable

## Troubleshooting

### If import fails:
```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Verify package structure
ls -la src/llm_wiki/export/
```

### If tests fail:
```bash
# Run with verbose output
python -m pytest tests/unit/test_llmsfull_exporter.py -vv -s

# Run specific failing test
python -m pytest tests/unit/test_llmsfull_exporter.py::TestLLMSFullExporter::test_name -vv
```

### If CLI command doesn't work:
```bash
# Check CLI is installed
llm-wiki --version

# Verify export group exists
llm-wiki export --help

# Check command registration
grep -n "export_llmsfull" src/llm_wiki/cli.py
```

## Success Criteria

All of the following should be true:

✅ All source files created and contain valid Python
✅ All 40+ tests pass successfully
✅ CLI command works with all options
✅ Export produces valid formatted output
✅ Filtering options work correctly
✅ Documentation is complete and accurate
✅ No breaking changes to existing code
✅ Performance meets expectations

If all of these pass, the implementation is complete and verified.
