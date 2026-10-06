from __future__ import annotations

import asyncio
import io
from pathlib import Path
from threading import Event

import anyio
import pytest
from app import catalog_photos
from app.catalog_photos import (
    MissingPhotoError,
    PhotoTooLargeError,
    UnsupportedPhotoError,
    remove_catalog_photo,
    save_catalog_photo,
    update_catalog_photo_framing,
)
from app.config import Settings
from app.db import Base, build_engine
from app.models import Coffee, Profile
from PIL import Image
from sqlalchemy.orm import Session


@pytest.fixture
def photo_context(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'photos.sqlite3'}")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            profile = Profile(display_name="Test brewer", pin_hash="unused")
            db.add(profile)
            db.flush()
            coffee = Coffee(roaster="Test roaster", name="Test coffee", created_by_id=profile.id)
            db.add(coffee)
            db.commit()
            yield settings, db, coffee
    finally:
        engine.dispose()


def png_content() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 20), "#8f4f38").save(output, format="PNG")
    return output.getvalue()


def test_save_raw_bytes_and_manage_photo_framing(photo_context) -> None:
    settings, db, coffee = photo_context
    content = png_content()
    settings.max_catalog_photo_bytes = len(content)
    settings.catalog_photo_max_dimension = 20
    asyncio.run(save_catalog_photo(content, settings, db, coffee, (0.2, 0.7, 1.5)))

    path = settings.catalog_upload_dir / Path(coffee.photo_path).name
    with Image.open(path) as image:
        assert image.format == "WEBP"
        assert image.size == (20, 10)
    assert coffee.photo_framing == {"focus_x": 0.2, "focus_y": 0.7, "zoom": 1.5}

    update_catalog_photo_framing(db, coffee, None)
    assert coffee.photo_framing is None
    remove_catalog_photo(settings, db, coffee)
    assert coffee.photo_path is None
    assert not path.exists()
    with pytest.raises(MissingPhotoError, match="Catalog item has no photo to frame"):
        update_catalog_photo_framing(db, coffee, (0.5, 0.5, 1))


@pytest.mark.parametrize("invalid_kind", ["bytes", "pixels", "animated", "malformed"])
def test_invalid_replacement_preserves_previous_photo(photo_context, invalid_kind) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee, (0.2, 0.7, 1.5)))
    old_path = coffee.photo_path
    old_file = settings.catalog_upload_dir / Path(old_path).name
    content = png_content()
    if invalid_kind == "bytes":
        settings.max_catalog_photo_bytes = len(content) - 1
        error, message = PhotoTooLargeError, "Photo exceeds"
    elif invalid_kind == "pixels":
        settings.max_catalog_photo_pixels = 100
        error, message = PhotoTooLargeError, "Photo resolution is too large"
    elif invalid_kind == "animated":
        output = io.BytesIO()
        Image.new("RGB", (5, 5), "red").save(
            output,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (5, 5), "blue")],
            duration=100,
            loop=0,
        )
        content = output.getvalue()
        error, message = UnsupportedPhotoError, "Animated photos are not supported"
    else:
        content = b"not an image"
        error, message = UnsupportedPhotoError, "Photo is not a valid supported image"

    with pytest.raises(error, match=message):
        asyncio.run(save_catalog_photo(content, settings, db, coffee))
    assert coffee.photo_path == old_path
    assert coffee.photo_framing == {"focus_x": 0.2, "focus_y": 0.7, "zoom": 1.5}
    assert list(settings.catalog_upload_dir.iterdir()) == [old_file]


def test_failed_replacement_preserves_previous_photo(photo_context, monkeypatch) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee, (0.2, 0.7, 1.5)))
    old_path = coffee.photo_path
    old_file = settings.catalog_upload_dir / Path(old_path).name

    def fail_commit() -> None:
        raise RuntimeError("Commit failed")

    with monkeypatch.context() as patch:
        patch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="Commit failed"):
            asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))

    assert coffee.photo_path == old_path
    assert coffee.photo_framing == {"focus_x": 0.2, "focus_y": 0.7, "zoom": 1.5}
    assert list(settings.catalog_upload_dir.iterdir()) == [old_file]


def test_refresh_failure_keeps_committed_photo(photo_context, monkeypatch) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))
    old_file = settings.catalog_upload_dir / Path(coffee.photo_path).name
    coffee_id = coffee.id

    def fail_refresh(_item) -> None:
        raise RuntimeError("Refresh failed")

    monkeypatch.setattr(db, "refresh", fail_refresh)
    with pytest.raises(RuntimeError, match="Refresh failed"):
        asyncio.run(save_catalog_photo(png_content(), settings, db, coffee, (0.2, 0.7, 1.5)))

    with Session(db.get_bind()) as verification_db:
        saved = verification_db.get(Coffee, coffee_id)
        new_file = settings.catalog_upload_dir / Path(saved.photo_path).name
        assert new_file.exists()
        assert not old_file.exists()
        assert saved.photo_framing == {"focus_x": 0.2, "focus_y": 0.7, "zoom": 1.5}


def test_refresh_failure_after_removal_cleans_up_file(photo_context, monkeypatch) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))
    old_file = settings.catalog_upload_dir / Path(coffee.photo_path).name
    coffee_id = coffee.id

    def fail_refresh(_item) -> None:
        raise RuntimeError("Refresh failed")

    monkeypatch.setattr(db, "refresh", fail_refresh)
    with pytest.raises(RuntimeError, match="Refresh failed"):
        remove_catalog_photo(settings, db, coffee)

    with Session(db.get_bind()) as verification_db:
        assert verification_db.get(Coffee, coffee_id).photo_path is None
    assert not old_file.exists()


@pytest.mark.parametrize("operation", ["remove", "frame"])
def test_failed_photo_update_rolls_back_state(photo_context, monkeypatch, operation) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee, (0.2, 0.7, 1.5)))
    old_path = coffee.photo_path
    old_file = settings.catalog_upload_dir / Path(old_path).name

    def fail_commit() -> None:
        raise RuntimeError("Commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Commit failed"):
        if operation == "remove":
            remove_catalog_photo(settings, db, coffee)
        else:
            update_catalog_photo_framing(db, coffee, (0.8, 0.4, 2))

    assert coffee.photo_path == old_path
    assert coffee.photo_framing == {"focus_x": 0.2, "focus_y": 0.7, "zoom": 1.5}
    assert list(settings.catalog_upload_dir.iterdir()) == [old_file]


def test_failed_atomic_write_preserves_previous_photo(photo_context, monkeypatch) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))
    old_path = coffee.photo_path
    old_file = settings.catalog_upload_dir / Path(old_path).name

    def fail_replace(_source, _destination) -> None:
        raise OSError("Disk write failed")

    monkeypatch.setattr(catalog_photos.os, "replace", fail_replace)
    with pytest.raises(OSError, match="Disk write failed"):
        asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))

    assert coffee.photo_path == old_path
    assert list(settings.catalog_upload_dir.iterdir()) == [old_file]


def test_cancellation_during_write_finishes_photo_transaction(photo_context, monkeypatch) -> None:
    settings, db, coffee = photo_context
    asyncio.run(save_catalog_photo(png_content(), settings, db, coffee))
    old_file = settings.catalog_upload_dir / Path(coffee.photo_path).name
    writing = Event()
    allow_write = Event()
    atomic_write = catalog_photos._atomic_write

    def paused_write(path: Path, content: bytes) -> None:
        writing.set()
        assert allow_write.wait(timeout=5)
        atomic_write(path, content)

    monkeypatch.setattr(catalog_photos, "_atomic_write", paused_write)

    async def cancel_during_write() -> None:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(save_catalog_photo, png_content(), settings, db, coffee)
            try:
                assert await anyio.to_thread.run_sync(writing.wait, 5)
                tasks.cancel_scope.cancel()
            finally:
                allow_write.set()

    anyio.run(cancel_during_write)
    new_file = settings.catalog_upload_dir / Path(coffee.photo_path).name
    assert new_file != old_file
    assert list(settings.catalog_upload_dir.iterdir()) == [new_file]
    with Session(db.get_bind()) as verification_db:
        assert verification_db.get(Coffee, coffee.id).photo_path == coffee.photo_path
