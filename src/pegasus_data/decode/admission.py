"""Machine-wide admission control for decode workers.

Each process that reads DATASUS (a notebook, a script, an agent) owns its own
:class:`~pegasus_data.decode.isolation.DecoderPool`, so N processes meant 4N
simultaneous decoders and the sum, not any one pool, exhausted the RAM
(measured 2026-10-05: ten workers at 4-9 GB each on a 32 GB machine, the disk
paging at 100%). A decode job therefore takes a **slot** before it starts:

* slots are files under the temp directory, held with an OS lock that the OS
  drops when the holder dies, so a killed process never strands one;
* the number of slots is machine-wide: ``PEGASUS_DECODE_SLOTS``, else
  ``total RAM // 8 GB + 1`` clamped to 2..6 (4 on a 32 GB machine);
* once it holds a slot the job waits while physical memory available to the
  OS is under a floor, ``PEGASUS_MIN_FREE_GB``, else ``max(4 GB, 15%)``.

A wait is bounded (``PEGASUS_ADMISSION_WAIT``, default 30 minutes): after that
the job runs anyway with a warning, because a decoder that never starts is a
worse failure than a slow machine.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

import psutil

__all__ = ["admitted", "free_floor_bytes", "slot_count"]

_GIB = 1024**3


def slot_count() -> int:
    override = os.environ.get("PEGASUS_DECODE_SLOTS")
    if override:
        return max(1, int(override))
    return max(2, min(6, psutil.virtual_memory().total // (8 * _GIB) + 1))


def free_floor_bytes() -> int:
    override = os.environ.get("PEGASUS_MIN_FREE_GB")
    if override:
        return int(float(override.replace(",", ".")) * _GIB)  # pt-BR shells write 0,2
    return int(max(4 * _GIB, 0.15 * psutil.virtual_memory().total))


def _slot_dir() -> Path:
    path = Path(os.environ.get("PEGASUS_DECODE_SLOT_DIR") or Path(tempfile.gettempdir()) / "pegasus_data_decode_slots")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _try_lock(handle) -> bool:  # noqa: ANN001
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle) -> None:  # noqa: ANN001
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _acquire_slot(deadline: float):  # noqa: ANN202
    directory, count = _slot_dir(), slot_count()
    while True:
        order = list(range(count))
        random.shuffle(order)
        for index in order:
            handle = open(directory / f"slot-{index}.lock", "a+b")  # noqa: SIM115 - held until release
            if _try_lock(handle):
                return handle
            handle.close()
        if time.monotonic() > deadline:
            return None
        time.sleep(0.2 + random.random() * 0.3)


@contextmanager
def admitted(label: str = ""):  # noqa: ANN201
    """Hold a machine-wide decode slot, and start only when memory allows."""
    wait = float(str(os.environ.get("PEGASUS_ADMISSION_WAIT", 1800)).replace(",", "."))
    started = time.monotonic()
    deadline = started + wait
    handle = _acquire_slot(deadline)
    try:
        floor = free_floor_bytes()
        while psutil.virtual_memory().available < floor:
            if time.monotonic() > deadline:
                warnings.warn(
                    f"decode of {label or 'a source'} started with only "
                    f"{psutil.virtual_memory().available / _GIB:.1f} GiB free after waiting {wait:.0f}s",
                    ResourceWarning, stacklevel=3,
                )
                break
            time.sleep(1.0 + random.random())
        yield
    finally:
        if handle is not None:
            _unlock(handle)
