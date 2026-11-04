#!/usr/bin/env python3
"""Stand-in for mperf-stat -p (github.com/tmcgilchrist/mperf): perf stat's
--delay -1/--control handshake, then perf 7.0's NDJSON once the target exits.
"""
import os, sys, time

args = sys.argv[1:]
events, out, target, json_out, ctl = [], None, None, False, None
i = 0
while i < len(args):
    a = args[i]
    if a == "-e": events += args[i + 1].split(","); i += 2
    elif a == "-o": out = args[i + 1]; i += 2
    elif a == "-p": target = int(args[i + 1]); i += 2
    elif a == "-j": json_out = True; i += 1
    elif a == "--delay": i += 2
    elif a == "--control": ctl = args[i + 1]; i += 2
    else:
        sys.stderr.write("Error: Unknown option '%s'\n" % a); sys.exit(1)
if target is None or out is None or not json_out:
    sys.stderr.write("fake mperf: expected -j -p PID -o FILE\n"); sys.exit(1)

KNOWN = {"cycles", "instructions", "branches", "branch-misses",
         "l1d-tlb-misses", "l1i-tlb-misses", "l2-tlb-misses-data",
         "l1d-cache-misses", "l1i-cache-misses", "map-stalls", "dispatch-stalls",
         "task-clock", "page-faults", "faults",
         "duration_time", "user_time", "system_time"}
for e in events:
    if e not in KNOWN:
        sys.stderr.write("Error: Unknown event '%s'\n" % e); sys.exit(1)

if ctl:
    ctl_path, ack_path = ctl[len("fifo:"):].split(",")
    with open(ctl_path, "rb", buffering=0) as c:
        while b"enable" not in c.read(64):
            pass
    with open(ack_path, "wb", buffering=0) as a:
        a.write(b"ack\n")

def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False

start = time.time()
while alive(target):
    time.sleep(0.01)
task_clock_ns = int((time.time() - start) * 1e9)

with open(out, "w") as f:
    for j, e in enumerate(events or ["cycles", "instructions"]):
        if e == "task-clock":
            value, unit, runtime = "%f" % (task_clock_ns / 1e6), "msec", task_clock_ns
        elif e in ("duration_time", "user_time", "system_time"):
            value, unit, runtime = "%f" % task_clock_ns, "", 1
        else:
            value, unit, runtime = "%f" % (1000000 * (j + 1)), "", task_clock_ns
        f.write('{"counter-value" : "%s", "unit" : "%s", "event" : "%s", '
                '"event-runtime" : %d, "pcnt-running" : 100.00}\n'
                % (value, unit, e, runtime))
