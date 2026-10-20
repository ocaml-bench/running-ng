"""Build-only command: compiles all benchmark binaries without running them."""
import logging
import sys
from typing import Dict, Set, Tuple
from running.suite import is_dry_run
from running.config import Configuration
from pathlib import Path
from running.util import parse_config_str
from running.runtime import Runtime
from running.command.runbms import (benchmark_build_jobs, build_affinity,
                                    default_build_jobs, expand_configs,
                                    prebuild, prebuild_roots)
from running.benchmark import set_build_log_dir
import os

logger = logging.getLogger(__name__)


def setup_parser(subparsers):
    parser = subparsers.add_parser(
        "buildbms",
        help="Build all benchmark binaries without running them",
    )
    parser.set_defaults(which="buildbms")
    parser.add_argument("CONFIG", type=Path, help="Configuration file")
    parser.add_argument("--build-jobs", type=int, default=None,
                        help="build up to N (benchmark, runtime) pairs at once "
                             "(default as for runbms)")


def run(args) -> bool:
    # Every command carries CONFIG; without this guard buildbms would intercept minheap.
    if args.get("which") != "buildbms":
        return False
    if "CONFIG" not in args or args["CONFIG"] is None:
        return False

    config_path = args["CONFIG"]
    configuration = Configuration.from_file(Path(os.getcwd()), config_path)
    requested = args.get("build_jobs")
    with build_affinity():
        prebuild_roots(configuration,
                       default_build_jobs() if requested is None else requested)
    configuration.resolve_class()

    suites = configuration.get("suites")
    benchmarks = configuration.get("benchmarks")
    if benchmarks is None:
        benchmarks = {}
    configs = expand_configs(
        configuration.get("configs"),
        configuration.get("config_sweep"),
    )

    runtime_by_config: Dict[str, Runtime] = {}
    for c in configs:
        runtime_by_config[c], _ = parse_config_str(configuration, c)

    unique_runtimes = {rt.name: rt for rt in runtime_by_config.values()}
    total_benchmarks = sum(len(bms) for bms in benchmarks.values())
    print(f"Building {total_benchmarks} benchmarks across "
          f"{len(unique_runtimes)} runtime(s): "
          f"{', '.join(unique_runtimes.keys())}")
    print()

    with build_affinity():
        jobs = benchmark_build_jobs(requested, benchmarks)
        if jobs > 1:
            set_build_log_dir(Path(os.environ.get("LOG_DIR", "build-logs")) / "build-logs")
        failed_why = prebuild(benchmarks, suites, configs, runtime_by_config,
                              jobs=jobs)
    build_failed: Set[Tuple[str, str, str]] = set(failed_why)
    prepared: Set[Tuple[str, str, str]] = {
        (s_, bm.name, runtime_by_config[c].name)
        for s_, bms in benchmarks.items() for bm in bms for c in configs
    } - build_failed
    print()
    print(f"--- Build summary ---")
    print(f"  Succeeded: {len(prepared)}")
    print(f"  Failed:    {len(build_failed)}")

    if build_failed:
        print(f"\n--- Build failures ({len(build_failed)}) ---")
        for suite_name, bm_name, rt_name in sorted(build_failed):
            print(f"  FAIL {suite_name}/{bm_name} [{rt_name}]")

    if prepared:
        print(f"\n--- Successful builds ({len(prepared)}) ---")
        for suite_name, bm_name, rt_name in sorted(prepared):
            print(f"  OK   {suite_name}/{bm_name} [{rt_name}]")

    if build_failed:
        sys.exit(1)
    return True
