from __future__ import annotations

import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from app.branding import LogoTooLargeError, UnsupportedLogoError, replace_logo_path, store_logo
from app.config import Settings
from app.db import Base, build_engine
from app.models import AppSettings
from PIL import Image
from sqlalchemy import event
from sqlalchemy.orm import Session


@pytest.fixture
def branding_context(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'branding.sqlite3'}"
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            item = AppSettings(id=1)
            db.add(item)
            db.commit()
            yield settings, db, item
    finally:
        engine.dispose()


def logo_content(format_name: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (40, 20), (143, 79, 56, 128)).save(output, format=format_name)
    return output.getvalue()


@pytest.mark.parametrize(
    ("format_name", "media_type"), [("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_store_raw_logo_preserves_contents(branding_context, format_name, media_type) -> None:
    settings, _db, _item = branding_context
    content = logo_content(format_name)
    settings.max_logo_bytes = len(content)
    path = asyncio.run(store_logo(content, media_type, settings, "logo"))
    assert path.startswith("/uploads/logo-")
    assert path.endswith(f".{format_name.lower()}")
    assert (settings.upload_dir / Path(path).name).read_bytes() == content


@pytest.mark.parametrize(
    "invalid_kind", ["media_type", "missing_type", "mismatch", "malformed", "bytes", "pixels"]
)
def test_invalid_logo_raises_domain_error_without_writing(branding_context, invalid_kind) -> None:
    settings, _db, _item = branding_context
    content = logo_content()
    media_type = "image/png"
    error, message = UnsupportedLogoError, "Logo must be PNG or WebP"
    if invalid_kind == "media_type":
        media_type = "image/jpeg"
    elif invalid_kind == "missing_type":
        media_type = None
    elif invalid_kind == "mismatch":
        media_type = "image/webp"
        message = "Logo contents do not match its file type"
    elif invalid_kind == "malformed":
        content = b"not an image"
        message = "Logo contents do not match its file type"
    elif invalid_kind == "bytes":
        settings.max_logo_bytes = len(content) - 1
        error, message = LogoTooLargeError, "Logo exceeds"
    else:
        settings.max_logo_pixels = 100
        error, message = LogoTooLargeError, "Logo dimensions are too large"

    with pytest.raises(error, match=message):
        asyncio.run(store_logo(content, media_type, settings, "brewing-logo"))
    assert list(settings.upload_dir.iterdir()) == [settings.catalog_upload_dir]


def test_shared_logo_is_kept_until_last_reference_is_removed(branding_context) -> None:
    settings, db, item = branding_context
    path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    file = settings.upload_dir / Path(path).name
    replace_logo_path(db, settings, item, "logo_path", path, created_upload=path)
    replace_logo_path(db, settings, item, "brewing_logo_path", path)

    replace_logo_path(db, settings, item, "logo_path", None)
    assert item.logo_path is None
    assert item.brewing_logo_path == path
    assert file.exists()

    replace_logo_path(db, settings, item, "brewing_logo_path", None)
    assert item.brewing_logo_path is None
    assert not file.exists()


def test_failed_logo_replacement_preserves_previous_file(branding_context, monkeypatch) -> None:
    settings, db, item = branding_context
    old_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    replace_logo_path(db, settings, item, "logo_path", old_path, created_upload=old_path)
    new_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))

    def fail_commit() -> None:
        raise RuntimeError("Commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Commit failed"):
        replace_logo_path(db, settings, item, "logo_path", new_path, created_upload=new_path)
    assert item.logo_path == old_path
    assert (settings.upload_dir / Path(old_path).name).exists()
    assert not (settings.upload_dir / Path(new_path).name).exists()


def test_failed_rollback_still_removes_uncommitted_upload(branding_context, monkeypatch) -> None:
    settings, db, item = branding_context
    path = asyncio.run(store_logo(logo_content(), "image/png", settings, "brewing-logo"))

    def fail_commit() -> None:
        raise RuntimeError("Commit failed")

    def fail_rollback() -> None:
        raise RuntimeError("Rollback failed")

    monkeypatch.setattr(db, "commit", fail_commit)
    monkeypatch.setattr(db, "rollback", fail_rollback)
    with pytest.raises(RuntimeError, match="Rollback failed"):
        replace_logo_path(db, settings, item, "brewing_logo_path", path, created_upload=path)
    assert not (settings.upload_dir / Path(path).name).exists()


def test_replacement_cleanup_requires_no_read_after_commit(branding_context, monkeypatch) -> None:
    settings, db, item = branding_context
    old_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    replace_logo_path(db, settings, item, "logo_path", old_path, created_upload=old_path)
    new_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    commit = db.commit
    block_reads = False

    def commit_then_fail_reads() -> None:
        nonlocal block_reads
        commit()
        block_reads = True

    def fail_reads(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        if block_reads and statement.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("Read failed")

    monkeypatch.setattr(db, "commit", commit_then_fail_reads)
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", fail_reads)
    try:
        replace_logo_path(db, settings, item, "logo_path", new_path, created_upload=new_path)
    finally:
        event.remove(engine, "before_cursor_execute", fail_reads)
    assert item.logo_path == new_path
    assert (settings.upload_dir / Path(new_path).name).exists()
    assert not (settings.upload_dir / Path(old_path).name).exists()


def test_replacement_uses_current_other_slot_reference(branding_context) -> None:
    settings, db, item = branding_context
    old_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    replace_logo_path(db, settings, item, "logo_path", old_path, created_upload=old_path)
    replace_logo_path(db, settings, item, "brewing_logo_path", old_path)
    assert item.logo_path == item.brewing_logo_path == old_path

    with Session(db.get_bind()) as other_db:
        other_item = other_db.get(AppSettings, item.id)
        replace_logo_path(other_db, settings, other_item, "brewing_logo_path", None)

    new_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    replace_logo_path(db, settings, item, "logo_path", new_path, created_upload=new_path)
    assert item.brewing_logo_path is None
    assert not (settings.upload_dir / Path(old_path).name).exists()
    assert (settings.upload_dir / Path(new_path).name).exists()


def test_failed_precommit_read_removes_uncommitted_upload(branding_context) -> None:
    settings, db, item = branding_context
    new_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    db.expire(item)

    def fail_reads(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("Read failed")

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", fail_reads)
    try:
        with pytest.raises(RuntimeError, match="Read failed"):
            replace_logo_path(db, settings, item, "logo_path", new_path, created_upload=new_path)
    finally:
        event.remove(engine, "before_cursor_execute", fail_reads)
    assert item.logo_path is None
    assert not (settings.upload_dir / Path(new_path).name).exists()


def test_concurrent_logo_replacements_keep_only_the_final_file(
    branding_context, monkeypatch
) -> None:
    settings, db, item = branding_context
    old_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    replace_logo_path(db, settings, item, "logo_path", old_path, created_upload=old_path)
    first_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    second_path = asyncio.run(store_logo(logo_content(), "image/png", settings, "logo"))
    first_ready_to_commit = Event()
    allow_first_commit = Event()
    second_started = Event()
    second_finished = Event()

    with (
        Session(db.get_bind(), expire_on_commit=False) as first_db,
        Session(db.get_bind(), expire_on_commit=False) as second_db,
    ):
        first_item = first_db.get(AppSettings, item.id)
        second_item = second_db.get(AppSettings, item.id)
        commit = first_db.commit

        def paused_commit() -> None:
            first_ready_to_commit.set()
            assert allow_first_commit.wait(timeout=10)
            commit()

        monkeypatch.setattr(first_db, "commit", paused_commit)

        def replace_second() -> None:
            second_started.set()
            replace_logo_path(
                second_db,
                settings,
                second_item,
                "logo_path",
                second_path,
                created_upload=second_path,
            )
            second_finished.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                replace_logo_path,
                first_db,
                settings,
                first_item,
                "logo_path",
                first_path,
                created_upload=first_path,
            )
            try:
                assert first_ready_to_commit.wait(timeout=10)
                second = executor.submit(replace_second)
                assert second_started.wait(timeout=10)
                assert not second_finished.wait(timeout=1)
            finally:
                allow_first_commit.set()
            first.result(timeout=10)
            second.result(timeout=10)

    db.refresh(item)
    assert item.logo_path == second_path
    assert list(settings.upload_dir.glob("logo-*")) == [
        settings.upload_dir / Path(second_path).name
    ]
