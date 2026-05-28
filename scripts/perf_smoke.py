"""Performance smoke test — concurrent requests via httpx.AsyncClient.

Not a full load test (use k6/Locust for that). Goal here is a quick latency
baseline for the public-without-auth endpoints (/livez, /readyz, /version,
/api/features) so we can spot regressions across deploys.

Reports p50/p95/p99/max + error rate per endpoint. No external deps beyond
httpx (already in requirements.txt).

Uso:
    # Baseline contra produção
    python -m scripts.perf_smoke \\
        --base https://nuclea-modeler-7474646973581105.aws.databricksapps.com \\
        --concurrency 10 --total 100

    # Contra dev local
    python -m scripts.perf_smoke --base http://localhost:8000 --total 50

Auth: nenhuma — só endpoints públicos. Endpoints autenticados são SSO-gated
e fora do escopo desse smoke.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from dataclasses import dataclass, field
from typing import Iterable

import httpx


# Endpoints públicos (sem auth Databricks). /readyz pode 401 dependendo da
# configuração de SSO — toleramos qualquer 200-499 como "respondeu".
DEFAULT_ENDPOINTS = (
    "/api/livez",
    "/api/version",
    # /api/readyz e /api/features podem ficar atrás de SSO — incluídos como
    # opcionais; ajuste com --endpoints se quiser focar.
)


@dataclass
class EndpointStats:
    path: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    statuses: dict[int, int] = field(default_factory=dict)

    def add(self, status: int, latency_ms: float, error: bool = False) -> None:
        self.statuses[status] = self.statuses.get(status, 0) + 1
        if error:
            self.errors += 1
        else:
            self.latencies_ms.append(latency_ms)

    @property
    def total(self) -> int:
        return sum(self.statuses.values()) + (self.errors if not self.statuses else 0)

    def pct(self, p: float) -> float | None:
        if not self.latencies_ms:
            return None
        s = sorted(self.latencies_ms)
        if len(s) == 1:
            return s[0]
        if p == 50:
            return statistics.median(s)
        k = max(0, min(len(s) - 1, int(p / 100 * (len(s) - 1))))
        return s[k]

    def summary(self) -> str:
        if not self.latencies_ms and not self.errors:
            return f"{self.path}: no data"
        p50 = self.pct(50)
        p95 = self.pct(95)
        p99 = self.pct(99)
        mx = max(self.latencies_ms) if self.latencies_ms else None
        ok = sum(c for s, c in self.statuses.items() if 200 <= s < 400)
        total = sum(self.statuses.values()) + self.errors
        return (
            f"{self.path:<28} "
            f"ok={ok:>4}/{total:<4} "
            f"err={self.errors:<3} "
            f"p50={_fmt(p50):>7} p95={_fmt(p95):>7} "
            f"p99={_fmt(p99):>7} max={_fmt(mx):>7} "
            f"statuses={dict(sorted(self.statuses.items()))}"
        )


def _fmt(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms:.1f}ms"


async def hit(client: httpx.AsyncClient, path: str, stats: EndpointStats) -> None:
    """One request, capture latency or error in the stats bag."""
    import time
    started = time.perf_counter()
    try:
        resp = await client.get(path)
        latency_ms = (time.perf_counter() - started) * 1000
        stats.add(resp.status_code, latency_ms)
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000
        stats.add(0, latency_ms, error=True)


async def run_endpoint(
    client: httpx.AsyncClient,
    path: str,
    total: int,
    concurrency: int,
) -> EndpointStats:
    stats = EndpointStats(path=path)
    sem = asyncio.Semaphore(concurrency)

    async def _one() -> None:
        async with sem:
            await hit(client, path, stats)

    await asyncio.gather(*(_one() for _ in range(total)))
    return stats


async def main_async(
    base: str,
    endpoints: Iterable[str],
    total: int,
    concurrency: int,
    timeout: float,
) -> int:
    headers = {"User-Agent": "nuclea-perf-smoke/1.0"}
    async with httpx.AsyncClient(
        base_url=base, timeout=timeout, follow_redirects=False, headers=headers
    ) as client:
        results: list[EndpointStats] = []
        for path in endpoints:
            stats = await run_endpoint(client, path, total, concurrency)
            results.append(stats)
            print(stats.summary())

    # Decide exit code: any endpoint with > 5% error rate or p95 > 2000ms fails.
    bad = []
    for r in results:
        total_reqs = len(r.latencies_ms) + r.errors
        if total_reqs == 0:
            continue
        err_rate = r.errors / total_reqs
        p95 = r.pct(95)
        if err_rate > 0.05:
            bad.append(f"{r.path}: error rate {err_rate:.1%} > 5%")
        if p95 is not None and p95 > 2000:
            bad.append(f"{r.path}: p95 {p95:.0f}ms > 2000ms budget")

    if bad:
        print("\nFAIL — orçamento estourado:", file=sys.stderr)
        for b in bad:
            print(f"  · {b}", file=sys.stderr)
        return 2
    print("\nOK — todos os endpoints dentro do orçamento.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Perf smoke (concurrent httpx GET).")
    parser.add_argument("--base", required=True, help="Base URL (ex: http://localhost:8000)")
    parser.add_argument("--endpoints", nargs="*", default=list(DEFAULT_ENDPOINTS))
    parser.add_argument("--total", type=int, default=100, help="Requests per endpoint")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    return asyncio.run(
        main_async(
            base=args.base.rstrip("/"),
            endpoints=args.endpoints,
            total=args.total,
            concurrency=args.concurrency,
            timeout=args.timeout,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
