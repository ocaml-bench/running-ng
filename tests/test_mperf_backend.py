"""The macOS counter path (mperf) on any POSIX host, against
tests/fixtures/fake_mperf.py, plus the macOS event groups. Cannot tell whether
the PMU counts on real hardware.
"""
import json
import os
import shutil
import stat
from pathlib import Path

import pytest
import yaml

from running import counters, osinfo
from running.benchmark import BinaryBenchmark, counter_seconds
from running.modifier import PerfAndOllyAttach

FAKE = Path(__file__).parent / "fixtures" / "fake_mperf.py"
CONFIG_DIR = Path(__file__).parent.parent / "src" / "running" / "config" / "base" / "ocaml"
BASE_CONFIGS = ["micro_base.yml", "macro_base.yml"]

#: What `mperf-stat -l` resolves on an Apple M5 (as7), plus mperf's software
#: and tool events. Extend only from a real Mac.
MPERF_EVENTS = {
    "cycles", "instructions", "branches", "branch-misses",
    "l1d-tlb-misses", "l1i-tlb-misses", "l2-tlb-misses-data",
    "l1d-cache-misses", "l1i-cache-misses", "map-stalls", "dispatch-stalls",
    "task-clock", "page-faults", "duration_time", "user_time", "system_time",
}

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not Path("/bin/sleep").exists(),
    reason="needs a POSIX host with /bin/sleep")


@pytest.fixture
def fake_mperf_on_path(tmp_path, monkeypatch):
    """Put a stand-in `mperf-stat` first on PATH and force the macOS backend."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    target = bindir / "mperf-stat"
    shutil.copy(FAKE, target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "{}{}{}".format(bindir, os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv(counters.BACKEND_ENV_VAR, "macos-mperf")
    return target


def _run(events):
    bm = BinaryBenchmark(Path("/bin/sleep"), ["1"], suite_name="s", name="smoke")
    mod = PerfAndOllyAttach(name="perf_grp1", type="PerfAndOllyAttach", val=events)
    _out, companion, status = bm._run_with_perf_and_olly(
        ["/bin/sleep", "1"], {}, None, mod)
    return json.loads(companion), status


def test_mperf_path_collects_counters_after_the_handshake(fake_mperf_on_path, caplog):
    data, status = _run("task-clock,page-faults,cycles,instructions")
    assert status.name == "Normal"
    assert data["counter_backend"] == "macos-mperf"
    by_name = {e["event"]: e for e in data["perf"]}
    assert set(by_name) == {"task-clock", "page-faults", "cycles", "instructions"}
    assert "handshake failed" not in caplog.text
    # mperf reports task-clock in msec, as perf 7.0 does
    assert 0.5 < counter_seconds(by_name["task-clock"]) < 5


def test_bad_event_list_degrades_without_failing_the_run(fake_mperf_on_path):
    data, status = _run("stalled-cycles-frontend")
    assert status.name == "Normal"
    assert data.get("perf") in ([], None)


def test_mperf_options_follow_the_tool_not_a_subcommand(tmp_path, monkeypatch):
    seen = []

    class Popen:
        def __init__(self, cmd, **kwargs):
            seen.append(cmd)
            raise OSError("not started")

    monkeypatch.setattr(counters.subprocess, "Popen", Popen)
    with pytest.raises(OSError):
        counters.MperfBackend().attach(42, str(tmp_path), ["cycles"],
                                       pin_prefix=["nice"])
    assert seen[0][:4] == ["nice", "mperf-stat", "--delay", "-1"]
    assert seen[0][-2:] == ["-e", "cycles"]


def test_unavailable_off_macos(monkeypatch):
    monkeypatch.setattr(osinfo, "IS_DARWIN", False)
    assert not counters.MperfBackend().available()


def test_a_non_setuid_install_is_unavailable_and_says_why(
        fake_mperf_on_path, monkeypatch, caplog):
    monkeypatch.setattr(osinfo, "IS_DARWIN", True)
    monkeypatch.setattr(counters, "_warned_mperf_not_setuid", False)
    monkeypatch.setattr(os, "geteuid", lambda: 501)
    assert not counters.MperfBackend().available()
    assert "chmod u+s" in caplog.text


def test_root_needs_no_setuid(fake_mperf_on_path, monkeypatch):
    monkeypatch.setattr(osinfo, "IS_DARWIN", True)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert counters.MperfBackend().available()


# --- event groups --------------------------------------------------------------

def _macos_groups(config):
    mods = yaml.safe_load((CONFIG_DIR / config).read_text())["modifiers"]
    return {name: (spec.get("val_macos") or spec["val"]).split(",")
            for name, spec in mods.items()
            if spec.get("type") == "PerfAndOllyAttach"
            and not name.endswith("_freebsd")}


@pytest.mark.parametrize("config", BASE_CONFIGS)
def test_every_macos_group_uses_only_mperf_events(config):
    # mperf rejects the whole list over one unknown name
    for name, events in _macos_groups(config).items():
        unknown = [e for e in events if e not in MPERF_EVENTS]
        assert not unknown, "{} in {} runs {} on macOS".format(name, config, unknown)


def test_both_base_configs_define_identical_macos_groups():
    assert _macos_groups("micro_base.yml") == _macos_groups("macro_base.yml")


def test_the_mperf_backend_reads_val_macos():
    m = PerfAndOllyAttach(name="perf_grp2", type="PerfAndOllyAttach",
                          val="stalled-cycles-frontend", val_macos="map-stalls")
    assert m.events_for(counters.MperfBackend.VAL_KEY) == ["map-stalls"]
