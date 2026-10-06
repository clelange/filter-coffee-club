"""Shared file storage primitives for uploaded images."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def upload_limit_label(limit: int) -> str:
    bytes_per_mb = 1024 * 1024
    return f"{limit // bytes_per_mb} MB" if limit % bytes_per_mb == 0 else f"{limit} bytes"
