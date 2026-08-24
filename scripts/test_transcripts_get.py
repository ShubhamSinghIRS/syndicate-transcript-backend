#!/usr/bin/env python3
import time
import httpx

BASE_URL = "http://localhost:8000"
ENDPOINT = "/api/transcripts"
CORS_ORIGIN = "http://localhost:5173"

HEADERS = {
    "Origin": CORS_ORIGIN,
    "Content-Type": "application/json"
}

def test_transcripts_response_time(runs=10):
    print(f"Benchmarking GET {BASE_URL}{ENDPOINT} ({runs} runs)...")
    print("--------------------------------------------------")
    
    latencies = []
    success_count = 0
    
    with httpx.Client(headers=HEADERS, timeout=15.0) as client:
        for i in range(1, runs + 1):
            start = time.perf_counter()
            try:
                resp = client.get(f"{BASE_URL}{ENDPOINT}")
                latency = (time.perf_counter() - start) * 1000  # in milliseconds
                
                if resp.status_code == 200:
                    latencies.append(latency)
                    success_count += 1
                    data = resp.json()
                    total_items = data.get("data", {}).get("meta", {}).get("total", "unknown")
                    print(f"  Run {i:02d}: {latency:.2f} ms (Status: 200 OK, Total transcripts in DB: {total_items})")
                else:
                    print(f"  Run {i:02d}: [FAILED] Status {resp.status_code}")
            except Exception as e:
                print(f"  Run {i:02d}: [ERROR] {e}")
            
            # 200ms sleep between requests to avoid triggering rate limit thresholds
            time.sleep(0.2)
            
    if latencies:
        min_lat = min(latencies)
        max_lat = max(latencies)
        avg_lat = sum(latencies) / len(latencies)
        
        print("\nResults Summary:")
        print("--------------------------------------------------")
        print(f"  Total Runs:         {runs}")
        print(f"  Successful Runs:    {success_count} ({success_count/runs*100:.1f}%)")
        print(f"  Min Response Time:  {min_lat:.2f} ms")
        print(f"  Max Response Time:  {max_lat:.2f} ms")
        print(f"  Avg Response Time:  {avg_lat:.2f} ms")
        print("--------------------------------------------------")
    else:
        print("\nAll runs failed.")

if __name__ == "__main__":
    test_transcripts_response_time()
