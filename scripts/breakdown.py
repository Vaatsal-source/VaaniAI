"""Split ONE request's latency into waiting / working / retrying from raw logs.
Usage: python scripts/breakdown.py <tag> [req_id]   (default: the slowest request by time-to-first-byte)
  waiting  = time spent in the limiter queue (enqueue->send gaps while no provider call is in flight)
  working  = provider calls (send->last_token) + local steps (retrieve, verify_det)
  retrying = backoff sleeps between attempts (+ the wasted provider time of failed attempts)
All timestamps are time.perf_counter() seconds (system-wide monotonic on one machine)."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
tag = sys.argv[1]
client = [json.loads(l) for l in open(ROOT / "logs" / f"load_{tag}.jsonl") if '"meta"' not in l]
server = [json.loads(l) for l in open(ROOT / "logs" / f"server_{tag}.jsonl")]
arr = {r["req"]: r["t"] for r in client if r["event"] == "arrive"}
fb = {r["req"]: r["t"] for r in client if r["event"] == "first_byte"}
end = {r["req"]: r["t"] for r in client if r["event"] in ("end", "abandon", "error")}
rid = sys.argv[2] if len(sys.argv) > 2 else max(fb, key=lambda k: fb[k] - arr[k])
ev = [e for e in server if e["req"] == rid]
t0 = arr[rid]
print(f"request {rid}: client arrive -> first byte = {(fb[rid]-t0)*1000:.1f} ms; -> end = {(end[rid]-t0)*1000:.1f} ms")
print(f"{'t_ms':>9}  event")
for e in ev:
    extra = {k: v for k, v in e.items() if k not in ("t", "req", "event", "answer", "question")}
    print(f"{(e['t']-t0)*1000:9.1f}  {e['event']} {extra}")
# classify intervals
calls, cur = [], None
for e in ev:
    if e["event"] == "send": cur = e
    if e["event"] == "last_token" and cur is not None:
        calls.append((cur["t"], e["t"], cur["step"], cur["attempt"])); cur = None
work_llm = sum(b - a for a, b, _, _ in calls)
retry_sleep = sum(e.get("backoff_ms", 0) for e in ev if e["event"] == "retry") / 1000
loc = 0.0; st = {}
for e in ev:
    if e["event"] == "step_start": st[e["step"]] = e["t"]
    if e["event"] == "step_end" and e["step"] == "retrieve": loc += e["t"] - st["retrieve"]
total = fb[rid] - t0
first_enq = ev[0]["t"]
queue_to_server = first_enq - t0
waiting = total - work_llm - loc - retry_sleep - queue_to_server
print(f"\nbefore server enqueue (network/ASGI): {queue_to_server*1000:8.1f} ms")
print(f"waiting (limiter queue / pacing)    : {waiting*1000:8.1f} ms")
print(f"working: provider calls             : {work_llm*1000:8.1f} ms  ({', '.join(f'{s}#{a}={ (b-a)*1000:.0f}ms' for a,b,s,_ in calls)})")
print(f"working: local retrieve             : {loc*1000:8.1f} ms")
print(f"retrying (backoff sleeps)           : {retry_sleep*1000:8.1f} ms")
print(f"sum = {(queue_to_server+waiting+work_llm+loc+retry_sleep)*1000:.1f} ms vs measured first-byte {total*1000:.1f} ms")
ft = [e for e in ev if e["event"] == "first_token"]
uf = [e for e in ev if e["event"] == "user_first_token"]
print("provider first_token events:", [(e['step'], e['ttft_ms']) for e in ft])
print("user_first_token at %.1f ms (released only after the deterministic check)" % ((uf[0]['t']-t0)*1000))
