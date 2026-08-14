"""Centralized functionality thats useful in multiple other files."""

import os
import random
import shutil
import string
import subprocess
import tempfile
from collections.abc import Generator, Iterable
from pathlib import Path

import platformdirs

pldirs = platformdirs.PlatformDirs("Duplicate Image Finder", "TheTimebreaker")
(pldirs.user_config_path / "error-files").mkdir(parents=True, exist_ok=True)


class Hashtable(dict[str, list[Path]]):
    """A dict mapping strings to list of Paths.

    This represents a map between a specific file hash and all the files that share this hash."""


class DuplicateGroup(list[Path]):
    """A list collecting Paths to files.

    This represents multiple files that were classified as 'being identically to one another'."""


def atomic_write(filepath: Path, data: str, encoding: str, newline: str | None = None) -> None:
    """Write data to a file atomically, creating a .bak backup if the file exists."""
    if filepath.is_dir():
        raise ValueError("Cannot write file contents to a directory.")

    if filepath.is_file():
        backup_path = filepath.with_suffix(filepath.suffix + ".bak")
        if backup_path.is_file():
            try:
                backup_path.unlink()
            except PermissionError:
                subprocess.run(["attrib", "-H", str(backup_path.resolve())], check=True)
                backup_path.unlink()
        shutil.copy2(filepath, backup_path)

    with tempfile.NamedTemporaryFile("w", encoding=encoding, dir=filepath.parent, delete=False, newline=newline) as tmp_file:
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


def all_subdirs(rootdirs: Path | Iterable[Path]) -> Generator[Path]:
    """Yields all root directory/directories and all their subdirectories recursively."""
    if isinstance(rootdirs, Path):
        rootdirs = [rootdirs]
    for rootdir in rootdirs:
        for dirpath, _dirnames, _filenames in os.walk(rootdir, followlinks=True):
            yield Path(dirpath)
