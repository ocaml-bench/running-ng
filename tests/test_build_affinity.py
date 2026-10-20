"""The build phase runs on every online CPU; measurement is left pinned."""
import os

import pytest

from running.command import runbms
from running import osinfo


linux_only = pytest.mark.skipif(
    not hasattr(os, "sched_getaffinity"),
    reason="CPU affinity is a Linux API")


@linux_only
def test_the_mask_is_restored_afterwards():
    before = os.sched_getaffinity(0)
    with runbms.build_affinity():
        pass
    assert os.sched_getaffinity(0) == before


@linux_only
def test_the_mask_is_restored_when_the_body_raises():
    before = os.sched_getaffinity(0)
    with pytest.raises(ValueError):
        with runbms.build_affinity():
            raise ValueError("build blew up")
    assert os.sched_getaffinity(0) == before


@linux_only
def test_the_build_phase_gets_every_online_cpu():
    online = set(osinfo.online_cpus())
    if not online or online <= os.sched_getaffinity(0):
        pytest.skip("nothing to widen: already on every online CPU")
    with runbms.build_affinity():
        assert os.sched_getaffinity(0) == online


@linux_only
def test_job_count_follows_the_mask_not_the_machine():
    """os.cpu_count() ignores affinity; a confined build must not oversubscribe."""
    before = os.sched_getaffinity(0)
    if len(before) < 2:
        pytest.skip("needs at least two usable CPUs")
    one = {sorted(before)[0]}
    try:
        os.sched_setaffinity(0, one)
        assert runbms.default_build_jobs() == 1
    finally:
        os.sched_setaffinity(0, before)


def test_the_job_count_stays_within_the_documented_range():
    assert 1 <= runbms.default_build_jobs() <= 16
