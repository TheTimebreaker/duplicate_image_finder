"""Contains all the functions that are used to generate hashtables, sort them into groups of duplicate files, sorting and deleting."""

import logging
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import imagesize
from PIL import UnidentifiedImageError
from send2trash import send2trash

from .hashfiles import ArchiveHashfile, Hashfile
from .utils import DuplicateGroup, Hashtable, all_subdirs


@dataclass
class DeletionCandidate:
    """An object collecting data about files, from which the best file will be kept and others will be deleted."""

    filepath: Path
    pixel_count: int
    is_file: bool
    filesize: int
    archive_object: ArchiveHashfile | None


class DeletionGroup(list[DeletionCandidate]):
    """A group of DeletionCandidates that were classified as 'being identically to one another'"""


def sort_deletion_candidates(
    candidates: DeletionGroup, *criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]]
) -> DeletionGroup:
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

    return DeletionGroup(sorted(candidates, key=key_func))


def combine_hashtables(*dicts: Hashtable) -> Hashtable:
    merged: Hashtable = Hashtable()
    for d in dicts:
        for k, v in d.items():
            merged.setdefault(k, []).extend(v)
    return merged


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


def iter_duplicate_groups(*hashtables: Hashtable) -> Generator[DuplicateGroup]:
    logging.info("Getting dupegroups... ")
    combined_hashtable = Hashtable()
    for hashtable in hashtables:
        combined_hashtable = combine_hashtables(combined_hashtable, hashtable)

    for files in combined_hashtable.values():
        if len(files) > 1:
            yield DuplicateGroup(files)

    logging.info("Getting dupegroups... Done!")


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


def get_deletion_group(
    duplicate_group: DuplicateGroup,
    *sorting_criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]],
) -> DeletionGroup:
    """Returns DeletionCandidate groups, sorted by the preferences set in sorting_criteria."""

    deletion_group_unsorted = DeletionGroup()
    for file in duplicate_group:
        extracted = extract_deletion_candidate(file)
        if extracted:
            deletion_group_unsorted.append(extracted)
    return sort_deletion_candidates(deletion_group_unsorted, *sorting_criteria)


def delete_deletion_group(deletion_group: DeletionGroup, deletion_method: Literal["rm", "recycle"] = "recycle") -> None:
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
