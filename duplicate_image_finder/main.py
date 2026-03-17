from pathlib import Path
from typing import Literal

from .duplicate_groups import delete_deletion_group, get_deletion_group, get_recursive_hashtable, iter_duplicate_groups


def find_and_delete_duplicates(
    path: Path,
    *sorting_criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]],
    deletion_method: Literal["rm", "recycle"] = "recycle",
) -> None:
    hashtable = get_recursive_hashtable(path)
    for duplicate_group in iter_duplicate_groups(hashtable):
        deletion_group = get_deletion_group(duplicate_group, *sorting_criteria)
        delete_deletion_group(deletion_group, deletion_method)
