"""Query latency baseline tests — NFR-P1 (≤200ms), NFR-P2 (≤2s), NFR-P3 (≤30s).

Run with:
    uv run pytest -m performance

Excluded from the default pytest run via ``addopts = ["-m", "not performance ...]``.

Deep query test uses httpx.AsyncClient with ASGITransport so asyncio.create_task()
background jobs share the event loop and can progress during anyio.sleep() yields.
TestClient runs the app in a separate thread, starving background tasks — do NOT
use it for the deep test.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.performance


def test_quick_query_under_200ms(seeded_wiki_client) -> None:
    """NFR-P1: POST /v1/query depth=quick returns in ≤200ms on a 100-page wiki."""
    start = time.perf_counter()
    response = seeded_wiki_client.post(
        "/v1/query",
        json={"query": "topic 5", "depth": "quick"},
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 200, (
        f"quick query expired its NFR-P1 budget: {elapsed_ms:.1f}ms vs 200ms "
        f"(history economy ≈ 1.2ms mean for 15k-page corpus)"
    )


def test_standard_query_under_2s(seeded_wiki_client) -> None:
    """NFR-P2: POST /v1/query depth=standard returns in ≤2s on a 100-page wiki."""
    start = time.perf_counter()
    response = seeded_wiki_client.post(
        "/v1/query",
        json={"query": "topic 3", "depth": "standard"},
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 2000, f"standard query took {elapsed_ms:.1f}ms (budget: 2000ms)"


@pytest.mark.anyio
async def test_deep_query_under_30s(seeded_wiki_app) -> None:
    """NFR-P3: full deep-query cycle (submit + poll until done) completes in ≤30s.

    Uses AsyncClient + anyio.sleep() so the asyncio.create_task() background job
    can run — TestClient would starve it. A timed_out result is valid; it means
    the synthesis hit its own 30s timeout but returned partial results within
    the NFR budget.
    """
    import anyio
    from httpx import ASGITransport, AsyncClient

    start = time.perf_counter()

    async with AsyncClient(
        transport=ASGITransport(app=seeded_wiki_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/query",
            json={"query": "topic 7", "depth": "deep"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        while True:
            await anyio.sleep(0.5)  # yield to event loop so background task progresses
            poll = await client.get(f"/v1/query/{job_id}")
            assert poll.status_code == 200
            data = poll.json()
            if data.get("status") in ("done", "timed_out", "failed", "error"):
                break
            elapsed = time.perf_counter() - start
            assert elapsed < 30, "deep query polling exceeded 30s budget"

    total_ms = (time.perf_counter() - start) * 1000
    assert total_ms < 30_000, f"deep query took {total_ms:.0f}ms (budget: 30000ms)"
    # timed_out is acceptable only if partial results were still returned;
    # a pure timed_out with zero results means the synthesis path is broken.
    assert data.get("status") == "done" or (
        data.get("status") == "timed_out" and data.get("partial", False)
    ), f"unexpected deep query status: {data.get('status')}"
