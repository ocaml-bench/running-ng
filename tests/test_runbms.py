import json

from running.command import runbms
from running.command.runbms import spread, expand_configs
import pytest


def test_spread_0():
    spread_factor = 0
    N = 8
    for i in range(0, N + 1):
        assert spread(spread_factor, N, i) == i


def test_spread_1():
    spread_factor = 1
    N = 8
    for i in range(1, N + 1):
        left = pytest.approx(spread(spread_factor, N, i) -
                             spread(spread_factor, N, i - 1))
        right = pytest.approx(1 + (i-1) / 7)
        assert left == right


def test_expand_configs_cartesian_respects_fixed_modifiers():
    configs = [
        "ocaml-v5.4|time_stats|d-1|s-32768|o-40|i-32|a-1",
        "ocaml-v5.4|time_stats|d-1|s-32768|i-32|a-1",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1",
    ]
    config_sweep = {
        "s": [32768, 65536],
        "o": [40, 60, 80],
    }

    expanded = expand_configs(configs, config_sweep)

    assert expanded == [
        "ocaml-v5.4|time_stats|d-1|s-32768|o-40|i-32|a-1",
        "ocaml-v5.4|time_stats|d-1|s-32768|i-32|a-1|o-40",
        "ocaml-v5.4|time_stats|d-1|s-32768|i-32|a-1|o-60",
        "ocaml-v5.4|time_stats|d-1|s-32768|i-32|a-1|o-80",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-32768|o-40",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-32768|o-60",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-32768|o-80",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-65536|o-40",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-65536|o-60",
        "ocaml-v5.4|time_stats|d-1|i-32|a-1|s-65536|o-80",
    ]


def test_expand_configs_without_sweep():
    configs = ["ocaml-v5.4|time_stats|d-1|s-32768|o-40|i-32|a-1"]
    assert expand_configs(configs, None) == configs


class _Runtime:
    def __init__(self, name):
        self.name = name


class _Bm:
    def __init__(self, name, fails=()):
        self.name, self.fails, self.calls = name, set(fails), []

    def prepare(self, runtime):
        self.calls.append(runtime.name)
        if runtime.name in self.fails:
            raise RuntimeError("boom")


def test_prebuild_reports_failures_and_builds_each_pair_once():
    from running.command.runbms import prebuild
    a, b = _Runtime("a"), _Runtime("b")
    ok, bad = _Bm("ok"), _Bm("bad", fails={"b"})
    # Two configs share runtime a: each (benchmark, runtime) is built once.
    configs = ["a|x", "a|y", "b|x"]
    by_config = {"a|x": a, "a|y": a, "b|x": b}
    failed = prebuild({"s": [ok, bad]}, {"s": None}, configs, by_config)
    assert set(failed) == {("s", "bad", "b")}
    assert failed[("s", "bad", "b")] == "boom"
    assert ok.calls == ["a", "b"]
    assert bad.calls == ["a", "b"]


def test_prebuild_rejects_unknown_suite():
    from running.command.runbms import prebuild
    with pytest.raises(KeyError):
        prebuild({"missing": [_Bm("x")]}, {}, ["a"], {"a": _Runtime("a")})


def test_build_failures_are_written_for_the_service(tmp_path):
    runbms.write_build_failures(tmp_path, {("macro-jsoo", "jsoo", "ocaml-trunk"): "exit 1"})
    data = json.loads((tmp_path / runbms.BUILD_FAILURES).read_text())
    assert data == {"build_failures": [{"suite": "macro-jsoo", "benchmark": "jsoo",
                                        "runtime": "ocaml-trunk", "reason": "exit 1"}]}


class _LoopRuntime:
    def __init__(self, name):
        self.name = name

    def is_oom(self, output):
        return False


class _LoopBm:
    suite_name = "s"
    timeout = 60
    memtrace_attach = None

    def __init__(self, name):
        self.name = name

    def attach_modifiers(self, mods):
        return self


class _LoopSuite:
    def is_passed(self, output):
        return True


def _run_loop(monkeypatch, tmp_path, results, invocations=2, resume=None):
    """run_one_benchmark over configs "a" and "b"; `results[config]` is the
    (exit status, return code) every invocation of that config gets."""
    from running.benchmark import SubprocessrExit
    monkeypatch.setattr(runbms, "plugins", {}, raising=False)
    monkeypatch.setattr(runbms, "configuration", None, raising=False)
    monkeypatch.setattr(runbms, "skip_oom", None, raising=False)
    monkeypatch.setattr(runbms, "skip_timeout", None, raising=False)
    monkeypatch.setattr(runbms, "resume", resume, raising=False)
    monkeypatch.setattr(runbms, "compress_logs", False, raising=False)
    monkeypatch.setattr(runbms, "is_dry_run", lambda: False)
    monkeypatch.setattr(runbms, "get_logged_in_users", lambda: set())
    monkeypatch.setattr(runbms, "parse_config_str",
                        lambda configuration, c: (_LoopRuntime("rt-" + c), []))

    def fake_run(c, b, runbms_dir, size, fd, **kw):
        status, rc = results[c]
        return b"", getattr(SubprocessrExit, status), rc
    monkeypatch.setattr(runbms, "run_benchmark_with_config", fake_run)
    runbms.run_one_benchmark(invocations, _LoopSuite(), _LoopBm("x"), None,
                             ["a", "b"], tmp_path, tmp_path)


def test_a_crashed_invocation_is_written_to_run_failures(tmp_path, monkeypatch):
    _run_loop(monkeypatch, tmp_path, {"a": ("Error", 1), "b": ("Normal", 0)})
    rows = runbms.read_run_failures(tmp_path)
    assert [(r["runtime"], r["invocation"], r["kind"], r["returncode"]) for r in rows] \
        == [("rt-a", 0, "error", 1), ("rt-a", 1, "error", 1)]
    assert rows[0]["benchmark"] == "x" and rows[0]["reason"] == "exit 1"


def test_a_failed_cell_is_not_marked_complete(tmp_path, monkeypatch):
    _run_loop(monkeypatch, tmp_path, {"a": ("Timeout", None), "b": ("Normal", 0)})
    complete = runbms.read_complete_cells(tmp_path)
    assert complete == {runbms.get_filename(_LoopBm("x"), None, None, "b")}
    assert runbms.read_run_failures(tmp_path)[0]["kind"] == "timeout"


def test_no_failures_writes_no_file(tmp_path, monkeypatch):
    _run_loop(monkeypatch, tmp_path, {"a": ("Normal", 0), "b": ("Normal", 0)})
    assert not (tmp_path / runbms.RUN_FAILURES).exists()


def test_a_rerun_cell_drops_its_earlier_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(runbms, "_native_emitter", None)
    a, b = (runbms.get_filename(_LoopBm("x"), None, None, c) for c in "ab")
    runbms.write_run_failures(tmp_path, [{"log": a, "kind": "error"},
                                         {"log": b, "kind": "error"}])
    runbms.discard_partial_cell(tmp_path, _LoopBm("x"), None, None, "a")
    assert runbms.read_run_failures(tmp_path) == [{"log": b, "kind": "error"}]
