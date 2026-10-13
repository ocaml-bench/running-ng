"""Parallel builds: when they are allowed, and what may run at the same time."""
import threading
import time

from running.command import runbms


class _Runtime:
    def __init__(self, name):
        self.name = name


class _Bm:
    """Records which builds of the same script overlapped."""

    def __init__(self, name, script, bench_dir, log, active, lock):
        self.name = name
        self.suite_name = "s"
        self.benchmark_dir = bench_dir
        self._script = script
        self._log, self._active, self._lock = log, active, lock

    def _resolve_build_script(self):
        return self._script

    def prepare(self, runtime):
        key = (self._script, runtime.name)
        with self._lock:
            self._active[key] = self._active.get(key, 0) + 1
            self._log.append(self._active[key])
        time.sleep(0.05)
        with self._lock:
            self._active[key] -= 1


def _tree(tmp_path, marked):
    (tmp_path / ".git").mkdir()
    if marked:
        (tmp_path / runbms.PARALLEL_MARKER).write_text("")
    d = tmp_path / "benchmarks" / "x"
    d.mkdir(parents=True)
    return d


def test_a_marked_tree_is_parallel_safe(tmp_path):
    bm = _Bm("a", "x.sh", _tree(tmp_path, True), [], {}, threading.Lock())
    assert runbms.parallel_safe(bm)


def test_an_unmarked_tree_builds_in_turn(tmp_path):
    bm = _Bm("a", "x.sh", _tree(tmp_path, False), [], {}, threading.Lock())
    assert not runbms.parallel_safe(bm)
    assert runbms.benchmark_build_jobs(None, {"s": [bm]}) == 1
    assert runbms.benchmark_build_jobs(8, {"s": [bm]}) == 1


def test_the_default_is_capped_at_16(tmp_path):
    bm = _Bm("a", "x.sh", _tree(tmp_path, True), [], {}, threading.Lock())
    assert 1 <= runbms.benchmark_build_jobs(None, {"s": [bm]}) <= 16
    assert runbms.benchmark_build_jobs(1, {"s": [bm]}) == 1


def test_one_script_for_one_runtime_never_builds_twice_at_once(tmp_path):
    log, active, lock = [], {}, threading.Lock()
    d = _tree(tmp_path, True)
    # three rungs of one tool, and a second tool, on two runtimes
    bms = [_Bm(n, "tool.sh", d, log, active, lock) for n in ("small", "default", "large")]
    bms.append(_Bm("other", "other.sh", d, log, active, lock))
    rts = {"a|x": _Runtime("a"), "b|x": _Runtime("b")}
    failed = runbms.prebuild({"s": bms}, {"s": object()}, list(rts), rts, jobs=8)
    assert failed == {}
    assert len(log) == 8 and max(log) == 1
