"""
Load test for POST /api/transcripts/filter (the search endpoint).

Run locally against the dev server:

    pip install locust
    locust -f load_tests/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089, set number of users + spawn rate, and start.
Locust's UI shows median/95th/99th percentile response time and failure rate live.

Note on the rate limit: /api/transcripts/filter is capped at 50 requests/60s
per source IP (stacked with a second global 50/60s-per-IP limit), see
src/apis/rate_limiting/limiter.py. Running this from one machine means every
simulated user shares the same IP, so total throughput is capped at ~50
req/min regardless of how many Locust users you spawn - that's expected,
not a bug. Use a small user count (5-10) with the default wait_time to see
normal latency, then push higher to watch 429s appear once you cross the
per-minute ceiling.
"""

import random

from locust import HttpUser, between, task

TOPICS = ["supply chain", "fintech", "healthcare", "AI", "retail", "operations", "logistics"]
DOMAINS = ["Technology", "Finance", "Healthcare", "Retail"]
GEOGRAPHIES = ["India", "United States", "Europe", "Southeast Asia"]


class SearchUser(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def search_free_text(self):
        # The main search box: full-text + trigram ranked search.
        self.client.post(
            "/api/transcripts/filter",
            json={"search": random.choice(TOPICS), "page": 1, "limit": 20},
            name="/api/transcripts/filter [search]",
        )

    @task(2)
    def filter_by_topic(self):
        # The separate substring "topic" param (ILIKE path).
        self.client.post(
            "/api/transcripts/filter",
            json={"topic": random.choice(TOPICS), "page": 1, "limit": 20},
            name="/api/transcripts/filter [topic]",
        )

    @task(2)
    def filter_by_domain_and_geography(self):
        self.client.post(
            "/api/transcripts/filter",
            json={
                "domains": [random.choice(DOMAINS)],
                "geographies": [random.choice(GEOGRAPHIES)],
                "page": 1,
                "limit": 20,
            },
            name="/api/transcripts/filter [domains+geographies]",
        )

    @task(1)
    def paginate_next_page(self):
        self.client.post(
            "/api/transcripts/filter",
            json={"search": random.choice(TOPICS), "page": random.randint(1, 5), "limit": 20},
            name="/api/transcripts/filter [pagination]",
        )
