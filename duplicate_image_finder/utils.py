"""Centralized functionality thats useful in multiple other files."""

import os
import random
import shutil
import string
import subprocess
import tempfile
from collections.abc import Generator, Iterable
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
        if backup_path.is_file():
            try:
                backup_path.unlink()
            except PermissionError:
                subprocess.run(["attrib", "-H", str(backup_path.resolve())], check=True)
                backup_path.unlink()
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


def make_temp_symlink_dir(paths: Iterable[Path]) -> Path:
    """
    Takes an iterable of pathlib.Path objects, creates a temporary directory,
    and fills it with symlinks to those paths (only if they are valid directories).

    Returns:
        Path to the temporary directory.
    """
    temp_dir = Path(tempfile.mkdtemp())
    for i, original_path in enumerate(paths):
        try:
            if not original_path.exists() or not original_path.is_dir():
                continue
            symlink_path = temp_dir / f"{original_path.name}_{i}"
            symlink_path.symlink_to(original_path)
        except Exception as e:
            print(f"Skipping {original_path}: {e}")
    return temp_dir


def delete_temp_symlink_dir(path: Path) -> None:
    for element in path.iterdir():
        element.unlink()
    path.rmdir()


def all_subdirs(rootdir: Path) -> Generator[Path]:
    """Yields the root directory and all its subdirectories recursively."""
    for dirpath, _dirnames, _filenames in os.walk(rootdir, followlinks=True):
        yield Path(dirpath)
