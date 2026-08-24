#!/usr/bin/env python3
import time
import httpx

BASE_URL = "http://localhost:8000"
ENDPOINT = "/api/transcripts/filter"
CORS_ORIGIN = "http://localhost:5173"

HEADERS = {
    "Origin": CORS_ORIGIN,
    "Content-Type": "application/json"
}

def benchmark_search():
    payload = {"search": "supply", "page": 1, "limit": 20}
    print(f"Benchmarking POST {ENDPOINT} with payload {payload}...")
    
    latencies = []
    
    with httpx.Client(headers=HEADERS, timeout=15.0) as client:
        for i in range(1, 6):
            start = time.perf_counter()
            try:
                resp = client.post(f"{BASE_URL}{ENDPOINT}", json=payload)
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    latencies.append(latency)
                    print(f"  Run {i}: {latency:.2f} ms")
                else:
                    print(f"  Run {i}: Failed with status {resp.status_code}")
            except Exception as e:
                print(f"  Run {i}: Error: {e}")
            time.sleep(0.2)
            
    if latencies:
        print(f"\nAverage Search Response Time: {sum(latencies)/len(latencies):.2f} ms (Min: {min(latencies):.2f} ms, Max: {max(latencies):.2f} ms)")

if __name__ == "__main__":
    benchmark_search()
