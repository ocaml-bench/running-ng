"""Which modifiers make two configs distinct in the contract."""
import logging

from running.contract.native import NativeEmitter

RUNTIMES = {"ocaml": {"type": "OCaml", "version": "5.5.1"}}
MODIFIERS = {
    "perf_grp1": {"type": "PerfAndOllyAttach", "measurement_only": True},
    "perf_grp2": {"type": "PerfAndOllyAttach", "measurement_only": True},
    "pin_bench": {"type": "CpuPin", "measurement_only": True},
    "jemalloc": {"type": "EnvVar", "var": "LD_PRELOAD", "val": "libjemalloc.so.2"},
    "malloc": {"type": "EnvVar", "var": "LD_PRELOAD", "val": "lib{0}.so"},
    "glibc_tuned": {"type": "ModifierSet", "val": "mmap32m|trim64m"},
    "s": {"type": "OCamlRunParam", "val": "s={0}"},
}


def _desc(tmp_path, config_str, modifiers=MODIFIERS):
    return NativeEmitter(tmp_path, "run", RUNTIMES, modifiers=modifiers)._descriptor(config_str)


def test_measurement_only_modifiers_do_not_split_configs(tmp_path):
    a = _desc(tmp_path, "ocaml|perf_grp1")
    b = _desc(tmp_path, "ocaml|perf_grp2|pin_bench")
    assert a["config_id"] == b["config_id"]
    assert "dimensions" not in a or not a["dimensions"]


def test_a_flag_modifier_splits_configs_under_its_own_name(tmp_path):
    base = _desc(tmp_path, "ocaml|perf_grp1")
    je = _desc(tmp_path, "ocaml|perf_grp1|jemalloc")
    assert je["config_id"] != base["config_id"]
    assert je["dimensions"] == {"jemalloc": True}


def test_a_name_value_modifier_is_an_axis(tmp_path):
    a = _desc(tmp_path, "ocaml|perf_grp1|malloc-jemalloc")
    b = _desc(tmp_path, "ocaml|perf_grp1|malloc-mimalloc")
    assert a["dimensions"] == {"malloc": "jemalloc"}
    assert a["config_id"] != b["config_id"]


def test_a_modifier_set_counts_as_one_flag(tmp_path):
    assert _desc(tmp_path, "ocaml|perf_grp1|glibc_tuned")["dimensions"] == {"glibc_tuned": True}


def test_registered_modifiers_keep_their_canonical_dimension(tmp_path):
    assert _desc(tmp_path, "ocaml|perf_grp1|s-32768")["dimensions"] == {"minor_heap": 32768}


def test_an_undeclared_modifier_splits_configs(tmp_path):
    a = _desc(tmp_path, "ocaml|perf_grp1", modifiers={})
    b = _desc(tmp_path, "ocaml|perf_grp2", modifiers={})
    assert a["config_id"] != b["config_id"]


def test_an_unmarked_observer_is_warned_about(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        NativeEmitter(tmp_path, "run", RUNTIMES,
                      modifiers={"perf_grp9": {"type": "PerfAndOllyAttach"}})
    assert "perf_grp9" in caplog.text
