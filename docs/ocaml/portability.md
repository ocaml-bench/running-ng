# Portability

running-ng runs on Linux, FreeBSD and macOS from the same configs. Each OS
produces the same kind of data, but the numbers are not comparable across
operating systems.

| | Linux | FreeBSD | macOS |
|---|---|---|---|
| Install | `install_deps.sh` | `install_deps.sh` (no root) | `install_deps.sh` |
| Hardware counters | `perf` | `pmcstat` (after `kldload hwpmc`) | none |
| task-clock | yes | no | no |
| CPU pinning (`CpuPin`) | `taskset` | `cpuset` | not available |
| olly and rusage | yes | yes | yes |

`perf_grp1/2/3` work on every OS, each using its own event names. Only
`perf_grp1` (cycles, instructions, page-faults) counts the same thing
everywhere; `perf_grp2` and `perf_grp3` are approximations between different
metrics, comparable only within one OS.

Note that while running-ng does CPU pinning when supported, reducing machine
noise (CPU frequency, core isolation, background services) is left to be
addressed at the machine level instead of inside running-ng.
