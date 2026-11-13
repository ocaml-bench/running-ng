import json
from pathlib import Path

import pytest

from running.benchmark import OCamlBuiltBinaryBenchmark
from running.runtime import OCaml


@pytest.mark.xfail(strict=True, reason=(
    "Tests an `existing_binary` / `existing_program_args` feature that has "
    "never existed in this repo: `git log -S existing_binary` over "
    "src/running/benchmark.py finds nothing on any branch, and "
    "OCamlBuiltBinaryBenchmark.__init__ swallows both into **kwargs, so "
    "prepare() falls through to a build and fails on the absent build script. "
    "Kept rather than deleted because what it describes (use a prebuilt "
    "binary, never resolve the runtime's executable) is a reasonable thing to "
    "want. strict=True so it flags itself the day someone implements it."))
def test_ocaml_built_binary_uses_existing_binary_without_runtime_resolution(tmp_path):
    bench_dir = tmp_path / "infer"
    bench_dir.mkdir()
    existing_binary = bench_dir / "infer-bin"
    existing_binary.write_text("#!/usr/bin/env bash\nexit 0\n")
    existing_binary.chmod(0o755)

    class NoRuntimeResolutionOCaml(OCaml):
        def get_executable(self) -> Path:
            raise AssertionError("Runtime executable must not be resolved")

    # `executable` keeps OCaml.__init__ from provisioning a switch; `version` is still recorded.
    placeholder = tmp_path / "unused-ocaml"
    placeholder.write_text("#!/usr/bin/env bash\nexit 0\n")
    placeholder.chmod(0o755)
    runtime = NoRuntimeResolutionOCaml(
        name="ocaml-v5.3", version="5.3.0", executable=str(placeholder))
    bm = OCamlBuiltBinaryBenchmark(
        benchmark_name="infer",
        benchmark_dir=bench_dir,
        build_script=None,
        binary=None,
        existing_binary=str(existing_binary),
        program_args=["fallback-arg"],
        existing_program_args=["analyze", "--no-report", "-j", "16"],
        build_args=[],
        build_env={},
        always_build=False,
        suite_name="ocaml-binarytrees",
        name="infer",
    )

    bm.prepare(runtime)
    cmd = [str(part) for part in bm.get_full_args(runtime)]
    assert cmd == [
        str(existing_binary.resolve()),
        "analyze",
        "--no-report",
        "-j",
        "16",
    ]


def test_ocaml_built_binary_falls_back_to_build_script_when_existing_missing(tmp_path):
    bench_dir = tmp_path / "infer"
    bench_dir.mkdir()
    build_script = bench_dir / "infer.build.sh"
    build_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "touch \"$RUNNING_OCAML_OUTPUT\"\n"
        "chmod +x \"$RUNNING_OCAML_OUTPUT\"\n"
    )
    build_script.chmod(0o755)

    fake_ocaml = tmp_path / "ocaml"
    fake_ocaml.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_ocaml.chmod(0o755)
    runtime = OCaml(name="ocaml-local", executable=str(fake_ocaml))

    bm = OCamlBuiltBinaryBenchmark(
        benchmark_name="infer",
        benchmark_dir=bench_dir,
        build_script=None,
        binary=None,
        existing_binary=str(bench_dir / "missing-infer"),
        program_args=["--build-fallback"],
        existing_program_args=["--existing"],
        build_args=[],
        build_env={},
        always_build=False,
        suite_name="ocaml-binarytrees",
        name="infer",
    )

    bm.prepare(runtime)
    built_binary = bench_dir / "_build_status" / "infer-ocaml-local"
    assert built_binary.exists()

    cmd = [str(part) for part in bm.get_full_args(runtime)]
    assert cmd == [str(built_binary.resolve()), "--build-fallback"]


def test_ocaml_built_binary_can_skip_runtime_executable_resolution(tmp_path):
    bench_dir = tmp_path / "infer"
    bench_dir.mkdir()
    build_script = bench_dir / "infer.build.sh"
    build_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "if [ -n \"${OCAML_EXECUTABLE:-}\" ]; then\n"
        "  echo \"OCAML_EXECUTABLE should not be set\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "touch \"$RUNNING_OCAML_OUTPUT\"\n"
        "chmod +x \"$RUNNING_OCAML_OUTPUT\"\n"
    )
    build_script.chmod(0o755)

    class NoRuntimeResolutionOCaml(OCaml):
        def get_executable(self) -> Path:
            raise AssertionError("Runtime executable must not be resolved")

    # `executable` keeps OCaml.__init__ from provisioning a switch; `version` is still recorded.
    placeholder = tmp_path / "unused-ocaml"
    placeholder.write_text("#!/usr/bin/env bash\nexit 0\n")
    placeholder.chmod(0o755)
    runtime = NoRuntimeResolutionOCaml(
        name="ocaml-v5.3", version="5.3.0", executable=str(placeholder))
    bm = OCamlBuiltBinaryBenchmark(
        benchmark_name="infer",
        benchmark_dir=bench_dir,
        build_script=build_script,
        binary=None,
        existing_binary=None,
        program_args=["--build-fallback"],
        existing_program_args=[],
        build_args=[],
        build_env={},
        use_runtime_executable=False,
        always_build=False,
        suite_name="ocaml-binarytrees",
        name="infer",
    )

    bm.prepare(runtime)
    built_binary = bench_dir / "_build_status" / "infer-ocaml-v5.3"
    assert built_binary.exists()

    cmd = [str(part) for part in bm.get_full_args(runtime)]
    assert cmd == [str(built_binary.resolve()), "--build-fallback"]


def _flaky_bench(tmp_path):
    bench_dir = tmp_path / "b"
    bench_dir.mkdir()
    script = bench_dir / "b.build.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'echo x >> "$RUNNING_OCAML_BENCH_DIR/calls"\n'
        '[ -e "$RUNNING_OCAML_BENCH_DIR/ok" ] || exit 1\n'
        'printf "#!/bin/sh\\n" > "$RUNNING_OCAML_OUTPUT"; chmod +x "$RUNNING_OCAML_OUTPUT"\n')
    placeholder = tmp_path / "ocaml"
    placeholder.write_text("#!/bin/sh\n")
    placeholder.chmod(0o755)
    runtime = OCaml(name="rt", version="5.4.1", executable=str(placeholder))
    bm = OCamlBuiltBinaryBenchmark(
        benchmark_name="b", benchmark_dir=bench_dir, build_script=None,
        binary=None, program_args=[], build_args=[], build_env={},
        always_build=False, suite_name="s", name="b")
    return bench_dir, runtime, bm


def test_failed_build_sentinel_blocks_until_retry(tmp_path):
    from running.benchmark import set_retry_failed_builds
    bench_dir, runtime, bm = _flaky_bench(tmp_path)
    calls = lambda: len((bench_dir / "calls").read_text().split())
    with pytest.raises(Exception):
        bm.prepare(runtime)
    assert calls() == 1
    with pytest.raises(RuntimeError, match="--retry-failed-builds"):
        bm.prepare(runtime)
    assert calls() == 1
    (bench_dir / "ok").touch()
    set_retry_failed_builds(True)
    try:
        bm.prepare(runtime)
    finally:
        set_retry_failed_builds(False)
    assert calls() == 2
    assert not list(bench_dir.glob("_build_status/*.build-failed"))


def test_failed_build_sentinel_from_another_compiler_is_stale(tmp_path):
    bench_dir, runtime, bm = _flaky_bench(tmp_path)
    with pytest.raises(Exception):
        bm.prepare(runtime)
    sentinel = next(bench_dir.glob("_build_status/*.build-failed"))
    assert sentinel.read_text().strip() == runtime.get_compiler_identity()
    # A failure recorded for a different compiler does not block this one.
    sentinel.write_text("0" * 40 + "\n")
    (bench_dir / "ok").touch()
    bm.prepare(runtime)
    assert len((bench_dir / "calls").read_text().split()) == 2
    assert not sentinel.exists()


def _counting_bench(tmp_path, bench_dir):
    bench_dir.mkdir(parents=True)
    (bench_dir / "b.build.sh").write_text(
        '#!/usr/bin/env bash\n'
        'echo x >> "$RUNNING_OCAML_BENCH_DIR/../calls"\n'
        'printf "#!/bin/sh\\n" > "$RUNNING_OCAML_OUTPUT"; chmod +x "$RUNNING_OCAML_OUTPUT"\n')
    placeholder = tmp_path / "ocaml"
    placeholder.write_text("#!/bin/sh\n")
    placeholder.chmod(0o755)
    runtime = OCaml(name="rt", version="5.4.1", executable=str(placeholder))

    def build():
        import running.benchmark as b
        b._git_state.clear()  # a new process
        OCamlBuiltBinaryBenchmark(
            benchmark_name="b", benchmark_dir=bench_dir, build_script=None,
            binary=None, program_args=[], build_args=[], build_env={},
            always_build=False, suite_name="s", name="b").prepare(runtime)
        return len((bench_dir.parent / "calls").read_text().split())
    return build


def _git(repo, *args):
    import subprocess
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    *args], check=True, capture_output=True)


def test_build_stamp_outside_git_rebuilds_only_for_another_runtime(tmp_path):
    build = _counting_bench(tmp_path, tmp_path / "b")
    assert build() == 1
    assert build() == 1
    stamp = json.loads((tmp_path / "b" / "_build_status" / "b-rt.build-stamp").read_text())
    assert set(stamp) == {"runtime"}
    stamp["runtime"] = "another"
    (tmp_path / "b" / "_build_status" / "b-rt.build-stamp").write_text(json.dumps(stamp))
    assert build() == 2


def test_binary_without_stamp_is_rebuilt(tmp_path):
    build = _counting_bench(tmp_path, tmp_path / "b")
    assert build() == 1
    (tmp_path / "b" / "_build_status" / "b-rt.build-stamp").unlink()
    assert build() == 2


def test_build_stamp_follows_commit_and_uncommitted_changes(tmp_path):
    repo = tmp_path / "repo"
    build = _counting_bench(tmp_path, repo / "b")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "one")
    assert build() == 1
    assert build() == 1
    stamp = json.loads((repo / "_build_status" / "b-rt.build-stamp").read_text())
    assert stamp["dirty"] == "" and len(stamp["commit"]) == 40
    (repo / "b" / "b.build.sh").write_text(
        (repo / "b" / "b.build.sh").read_text() + "# edit\n")
    assert build() == 2          # uncommitted change
    assert build() == 2
    (repo / "b" / "input.txt").write_text("x")
    assert build() == 3          # untracked file in the benchmark's directory
    (repo / "notes").write_text("x")
    assert build() == 3          # changes elsewhere count only once committed
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "two")
    assert build() == 4          # new commit, clean tree
    assert build() == 4


def test_build_status_ignores_itself(tmp_path):
    repo = tmp_path / "repo"
    build = _counting_bench(tmp_path, repo / "b")
    _git(repo, "init", "-q")
    _git(repo, "add", "b")
    _git(repo, "commit", "-qm", "one")
    build()
    assert (repo / "_build_status" / ".gitignore").read_text() == "*\n"
    import subprocess
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "_build_status"],
                         capture_output=True, text=True, check=True).stdout
    assert out == ""


def test_stale_setup_runs_make_setup_once(tmp_path):
    from running.command.runbms import ensure_setup
    import running.benchmark as b
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "b").mkdir()
    (repo / "scripts" / "setup-stamp.sh").write_text('[ -e done ]\n')
    (repo / "Makefile").write_text('setup:\n\techo "$$SKIP_TEST_BUILD" >> done\n')
    _git(repo, "init", "-q")
    b._git_state.clear()

    class Bm:
        benchmark_dir = repo / "b"
    ensure_setup([Bm(), Bm()])
    assert (repo / "done").read_text() == "1\n"
    ensure_setup([Bm()])
    assert (repo / "done").read_text() == "1\n"
    (repo / "Makefile").write_text('setup:\n\texit 3\n')
    (repo / "done").unlink()
    with pytest.raises(RuntimeError, match="make setup failed"):
        ensure_setup([Bm()])
