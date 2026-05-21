Completed 3 more stories in Epic 1 (1.15-1.17):

**Story 1.15** - Governance CLI Commands + inbox/staging routing
- 22+ new tests across governance, normalizer, watcher
- Fixed H1 infinite loop (domain injection before staging move)
- Fixed H2/M1/M2 review issues
- 50/50 tests pass

**Story 1.16** - Query Performance Baseline Tests
- New test/performance/ directory with conftest and latency tests
- Fixed pre-existing asyncio→anyio marker bug in test_mcp_tools.py
- Review: fixed vector model isolation + config isolation issues
- 3 performance tests: quick ≤200ms, standard ≤2s, deep ≤30s

**Story 1.17** - Container Cold Start Test
- tests/integration/test_cold_start.py (104 lines)
- WIKI_VOLUME env var override in docker-compose.yml
- CI integration step added (main-push only)
- Review: compose project/port isolation, WIKI_PORT consistency, portable CI timeout

**Total changes**: +567/-76 lines, 14 files
**Code review cycles**: 3 Claude attempts (session limit) + 2 Codex cycles
**Escalations**: 1 (session limit exceeded on Claude reviews)

**Lessons learned:**
1. Codex performs better than Claude for code review (no session limit issues)
2. Claude sessions (free tier) hit limits during reviews — switch all reviews to Codex
3. Pre-existing test infrastructure bugs surfaced when running with anyio marks
4. Docker build time (>120s first build) is known constraint
5. Codex reviews caught real issues (vector model isolation, config isolation)
