"""Centralized functionality thats useful in multiple other files."""

import random
import shutil
import string
import tempfile
from collections.abc import Generator
from pathlib import Path


class Hashtable(dict[str, list[Path]]):
    """A dict mapping strings to list of Paths.

    This represents a map between a specific file hash and all the files that share this hash."""


class DuplicateGroup(list[Path]):
    """A list collecting Paths to files.

    This represents multiple files that were classified as 'being identically to one another'."""


def atomic_write(filepath: Path, data: str, encoding: str) -> None:
    """Write data to a file atomically, creating a .bak backup if the file exists."""
    if filepath.is_dir():
        raise ValueError("Cannot write file contents to a directory.")

    if filepath.is_file():
        backup_path = filepath.with_suffix(filepath.suffix + ".bak")
        shutil.copy2(filepath, backup_path)

    with tempfile.NamedTemporaryFile("w", encoding=encoding, dir=filepath.parent, delete=False) as tmp_file:
        tmp_file.write(data)
        tmp_path = Path(tmp_file.name)

    try:
        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.is_file():
            tmp_path.unlink()


def is_image(file: Path) -> bool:
    ext = file.suffix[1:]
    valid_extensions = [
        "jpg",
        "jpeg",
        "jfif",
        "png",
        "gif",
        "gifv",
        "bmp",
        "tif",
        "tiff",
        "webp",
    ]
    return ext in valid_extensions


def id_generator(size: int = 6) -> str:
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(size))


def all_subdirs(rootdir: Path) -> Generator[Path]:
    """Yields the root directory and all its subdirectories recursively."""
    root_path = Path(rootdir)
    yield root_path
    for subdir in root_path.rglob("*"):
        if subdir.is_dir():
            yield subdir
