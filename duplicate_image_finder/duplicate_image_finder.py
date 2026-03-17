"""..."""  # TODO

import logging
import os
import random
import shutil
import string
import tempfile
import time
import traceback
from collections.abc import Generator
from pathlib import Path
from typing import Any, Literal, Optional, overload, TypedDict
from dataclasses import dataclass

import imagehash
import imagesize
from pandas import DataFrame
from PIL import Image, ImageFile, UnidentifiedImageError
from send2trash import send2trash

from . import base64custom

Image.MAX_IMAGE_PIXELS = None
Image.warnings.simplefilter("ignore", Image.DecompressionBombWarning)
ImageFile.LOAD_TRUNCATED_IMAGES = True


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


class Hashfile:
    """Main class that contains hashes of files of specified folder.
    Will load existing hashes, generate missing ones and write those to disk.
        path: Full path to directory
    """

    def __init__(self, path: Path, ignore_hashfiles: bool = False) -> None:
        self.path = path
        self.noprint = True
        self.basename = "!hashes"
        self.ext = ".csv"
        self.other_hashfilepaths: list[Path] = []
        self.hashpath = self.path / (self.basename + self.ext)

        self.data: dict[str, tuple[str, int | None, int | None, int | None]] = {}
        self.hashfile_changes = False
        if not ignore_hashfiles:
            self._read_hashes()
        self._generate_hashes()

    def _remove_other_hashfiles(self) -> None:
        for p in self.other_hashfilepaths:
            send2trash(p)

    def _read_single_hashfile(self, file: Path) -> Generator[tuple[str, str, int | None, int | None, int | None]]:
        with open(file, encoding="utf-8-sig") as f:
            for line in f.read().split("\n"):
                values = line.split(",")
                try:
                    filename, filehash = values
                    yield filename, filehash, None, None, None
                except ValueError:
                    try:
                        filename, filehash, pixel_height, pixel_length, filesize = values
                        yield filename, filehash, int(pixel_height), int(pixel_length), int(filesize)
                    except ValueError as e:  # skips empty lines and others that cant be read properly
                        if not line:  # empty line in text document
                            continue
                        else:
                            logging.error(
                                "ValueError when reading hashfile file = %s : %s",
                                file,
                                traceback.format_exception(e),
                            )
                            if self.hashfile_changes is False:
                                self.hashfile_changes = True
                            continue

    def _read_hashes(self) -> None:
        allfiles_filenames: set[str] = set()
        hashfiles: list[Path] = []
        for file in self.path.iterdir():
            if not file.is_file():
                continue
            if self.basename in file.name and self.ext in file.name and not file.name.endswith(".bak"):
                hashfiles.append(file)
            else:
                allfiles_filenames.add(file.name)

        for hashfile in hashfiles:
            for filename, filehash, pixel_height, pixel_length, filesize in self._read_single_hashfile(hashfile):
                if not self.file_for_hash_exists(filename, allfiles_filenames):
                    self.hashfile_changes = True
                elif filename in self.data:  # removes conflicting hashes
                    if self.data[filename][0] != filehash:
                        self.data.pop(filename)
                else:
                    self.data[filename] = (filehash, pixel_height, pixel_length, filesize)

            if hashfile.name != self.basename + self.ext:
                self.other_hashfilepaths.append(hashfile)

        self._write_hashes()
        self._remove_other_hashfiles()

    def file_for_hash_exists(self, filepath: str, allfiles: set[str]) -> bool:
        return filepath in allfiles

    def _write_hashes(self) -> bool:
        if self.hashfile_changes is False:
            return True
        lines_table = [[filename, *list(map(str, table))] for filename, table in self.data.items()]
        lines_strings = [f"{','.join(line)}" for line in lines_table]
        content_string = "\n".join(lines_strings)
        atomic_write(self.hashpath, content_string, "utf-8-sig")
        self.hashfile_changes = False
        return True

    def _generate_hashes(self) -> None:
        """Generates hashes for all files in folder and saves them into a hash file that gets used for later runs to cut down processing."""
        last_save = time.time()
        with os.scandir(self.path) as directory:
            for file in directory:
                if file.name in self.data:  # Skips files that already have a stored hash
                    continue

                filepath = file.path
                if "," in file.name:
                    try:
                        new_filepath = os.path.join(self.path, file.name.replace(",", "_"))
                        os.rename(filepath, new_filepath)
                        filepath = new_filepath
                    except FileExistsError:
                        os.remove(filepath)
                        filepath = new_filepath
                if is_image(filepath):  # warum schlägt das hier nicht an???
                    try:
                        self.data[file.name] = (generate_image_hash(filepath), None, None, None)
                        if self.hashfile_changes is False:
                            self.hashfile_changes = True

                    except UnidentifiedImageError, OSError, UserWarning:
                        logging.error(
                            "An error occured while generating hash of file %s. Moved to %s .",
                            filepath,
                            r"G:\Documents\Visual Studio Code projects\Downloader\!error_files",
                        )
                        shutil.move(
                            filepath,
                            os.path.join(
                                r"G:\Documents\Visual Studio Code projects\Downloader\!error_files",
                                file.name,
                            ),
                        )

                if time.time() - last_save > 30:  # Saves every ~30 seconds
                    self._write_hashes()
                    last_save = time.time()
        self._write_hashes()

    def get_fullpath_image(self, filename: str) -> Path:
        return self.path / filename

    def fullpath_key_value(self) -> Hashtable:
        """Returns dictionary with key: hash and value: fullpath to file."""
        result: Hashtable = Hashtable()
        for filename, elements in self.data.items():
            filehash = elements[0]
            if filehash in result:
                result[filehash].append(self.get_fullpath_image(filename))
            else:
                result[filehash] = [self.get_fullpath_image(filename)]
        return result


class ArchiveHashfile(Hashfile):
    """Main class that loads archive hashes of specified folder.
    path: Full path to directory
    """

    def __init__(self, path: Path) -> None:
        self.folder = path
        self.basename = "!archival-hashes"
        self.ext = ".csv"
        self.hashpath = self.folder / (self.basename + self.ext)
        self.data: dict[str, tuple[str, int | None, int | None, int | None]] = {}
        self.other_hashfilepaths: list[Path] = []
        self.hashfile_changes = False
        self._read_hashes()

    def set_data(self, new_data: dict[str, tuple[str, int | None, int | None, int | None]]) -> None:
        self.data = new_data
        self._write_hashes()

    def get_fullpath_image(self, filename: str) -> Path:
        return super().get_fullpath_image(f"archiveHash_{filename}")

    def file_for_hash_exists(self, filepath: str, allfiles: set[str]) -> Literal[True]:  # noqa: ARG002
        return True

    def archive_folder(self, delete_source: bool = False) -> None:
        def remove_files(files: list[Path]) -> None:
            logging.info("Removing files after archiving...")
            for file in files:
                try:
                    file.unlink()
                except FileNotFoundError:
                    continue
            logging.info("Removing files after archiving... Done!")

        hashes = Hashfile(self.folder)
        rm_files: list[Path] = []
        self.hashfile_changes = True
        for i, filepath in enumerate(self.folder.iterdir()):
            logging.info("Generating archive hashes, dimensions and filesize (#%s)... ", str(i))
            if not is_image(filepath):
                continue

            filename = f"{id_generator(6)}.png"
            while filename in self.data.keys():
                filename = f"{id_generator(6)}.png"

            filehash = hashes.data[filepath.name][0]
            try:
                width, height = imagesize.get(filepath)
                filesize = filepath.stat().st_size
                self.data[filename] = (filehash, int(height), int(width), filesize)
            except UnidentifiedImageError, OSError:
                logging.error("Error encountered on %s that prevents hashing.", str(filepath))

            rm_files.append(filepath)

        self._write_hashes()
        rm_files.append(self.folder / "!hashes.csv")

        if delete_source:
            remove_files(rm_files)

    def remove_entry(self, filename: str) -> None:
        if filename in self.data.keys():
            self.data.pop(filename)
            self.hashfile_changes = True
        self._write_hashes()


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


def generate_image_hash(file: str) -> str:
    return str(
        base64custom.Base64(
            int(
                str(imagehash.phash(Image.open(file), hash_size=16, highfreq_factor=8)),
                16,
            )
        )
    )


def all_subdirs(rootdir: Path) -> Generator[Path]:
    """Yields the root directory and all its subdirectories recursively."""
    root_path = Path(rootdir)
    yield root_path
    for subdir in root_path.rglob("*"):
        if subdir.is_dir():
            yield subdir


def combine_hashtables(*dicts: Hashtable) -> Hashtable:
    merged: Hashtable = Hashtable()
    for d in dicts:
        for k, v in d.items():
            merged.setdefault(k, []).extend(v)
    return merged


class Hashtable(dict[str, list[Path]]):
    """A dict mapping strings to list of Paths.

    This represents a map between a specific file hash and all the files that share this hash."""


def get_recursive_hashtable(path: Path) -> Hashtable:
    """Loads/Generates the Hashtable of all files contained in path and its subdirectories."""
    logging.info("Loading hashes from %s... ", path)
    all_hashes: list[Hashtable] = []
    for directory in all_subdirs(path):
        hashes = Hashfile(path=directory)
        all_hashes.append(hashes.fullpath_key_value())

        archive = ArchiveHashfile(path=directory)
        all_hashes.append(archive.fullpath_key_value())

    logging.info("Loading hashes from %s... Done!", path)
    return combine_hashtables(*all_hashes)


class DuplicateGroup(list[Path]):
    """A list collecting Paths to files.

    This represents multiple files that were classified as 'being identically to one another'."""


@dataclass
class DeletionCandidate:
    """An object collecting data about files, from which the best file will be kept and others will be deleted."""

    filepath: Path
    pixel_count: int
    is_file: bool
    filesize: int
    archive_object: ArchiveHashfile | None


def sort_deletion_candidates(
    candidates: list[DeletionCandidate], *criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]]
) -> list[DeletionCandidate]:
    def key_func(obj: DeletionCandidate) -> tuple[Any]:
        key: list[Any] = []
        for field, order in criteria:
            value = getattr(obj, field)

            # For descending, invert value
            if order == "descending":
                try:
                    value = -value
                except TypeError:  # fallback: use tuple trick
                    value = (0, value)
            key.append(value)
        return tuple(key)

    return sorted(candidates, key=key_func)


def get_duplicate_groups(*hashtables: Hashtable) -> list[DuplicateGroup]:
    logging.info("Getting dupegroups... ")
    combined_hashtable = Hashtable()
    for hashtable in hashtables:
        combined_hashtable = combine_hashtables(combined_hashtable, hashtable)

    duplicate_groups: list[DuplicateGroup] = []
    for files in combined_hashtable.values():
        if len(files) > 1:
            duplicate_groups.append(DuplicateGroup(files))

    logging.info("Getting dupegroups... Done!")
    return duplicate_groups


def extract_deletion_candidate(file: Path) -> DeletionCandidate | Literal[False]:
    """Extracts a DeletionCandidate object from a given file. Returns False if not possible."""
    try:
        width, height = imagesize.get(file)
        pixel_count = int(width * height)
        return DeletionCandidate(filepath=file, pixel_count=pixel_count, is_file=True, filesize=file.stat().st_size, archive_object=None)
    except UnidentifiedImageError, ValueError:
        logging.error("UnidentifiedImageError or ValueError: Cannot identify file %s.", file)
        return False
    except FileNotFoundError:
        try:
            if file.name.startswith("archiveHash_"):
                archive = ArchiveHashfile(path=file.parent)
                elements = archive.data[file.name.replace("archiveHash_", "")]
                _filename, pixel_height, pixel_length, size = elements
                if pixel_height is None or pixel_length is None or size is None:
                    raise TypeError("An archive hash returned None type elements, which shouldn't happen, ever.")
                return DeletionCandidate(
                    filepath=file,
                    pixel_count=pixel_height * pixel_length,
                    is_file=False,
                    filesize=size,
                    archive_object=archive,
                )
            logging.error("File %s could not be fetched neither as a file nor in the archive.", file.name)
            return False
        except KeyError:
            logging.error("KeyError for file %s in Archive %s .", file.name, file.parent)
            return False


def iter_deletion_groups(
    duplicate_groups: list[DuplicateGroup],
    *sorting_criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]],
) -> Generator[list[DeletionCandidate]]:
    """Yields DeletionCandidate groups, sorted by the preferences set in sorting_criteria."""

    duplicate_groups_len = len(duplicate_groups)
    if duplicate_groups_len == 0:
        logging.info("No duplicates found, so there's nothing to delete!")
        return

    for duplicate_group in duplicate_groups:
        deletion_candidates_unsorted: list[DeletionCandidate] = []
        for file in duplicate_group:
            extracted = extract_deletion_candidate(file)
            if extracted:
                deletion_candidates_unsorted.append(extracted)
        yield sort_deletion_candidates(deletion_candidates_unsorted, *sorting_criteria)


def delete_deletion_group(deletion_group: list[DeletionCandidate], deletion_method: Literal["rm", "recycle"]) -> None:
    for i, deletion_candidate in enumerate(deletion_group):
        is_first_file = i == 0
        filepath = deletion_candidate.filepath

        if is_first_file:
            pass
        elif filepath.name.startswith("archiveHash_"):
            hashfilekey = filepath.name.replace("archiveHash_", "")
            if deletion_candidate.archive_object is None:
                raise ValueError("The archive object of a file marked as an archived file was unexpectedly empty.")
            deletion_candidate.archive_object.remove_entry(hashfilekey)
        else:
            if deletion_method == "rm":
                filepath.unlink()
            elif deletion_method == "recycle":
                send2trash(filepath)


if __name__ == "__main__":
    pass
