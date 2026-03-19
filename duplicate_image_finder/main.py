from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from .duplicate_groups import delete_deletion_group, get_deletion_group, get_recursive_hashtable, iter_duplicate_groups
from .utils import delete_temp_symlink_dir, make_temp_symlink_dir


def find_and_delete_duplicates(
    paths: Path | Iterable[Path],
    deletion_method: Literal["rm", "recycle"] = "recycle",
    *sorting_criteria: tuple[Literal["pixel_count", "is_file", "filesize"], Literal["ascending", "descending"]],
) -> None:
    """Will hash all files recursively (including subdirectories) in given path, find duplication groups
    and delete them based on your sorting_criteria and deletion_method.

    Keep in mind: the sorting_criteria will sort the list of files and the FIRST element
    will be kept. Make sure the first element is "the best" (whatever that means for you).

    Args:
        path (Path): Directory path from which duplicates will be searched for.
        deletion_method (Literal[&quot;rm&quot;, &quot;recycle&quot;], optional):
        rm: Permanent deletion.
        Recycle: Send to trash bin. Defaults to "recycle".
        *sorting_criteria: Tuples that decide the sorting.
    """
    if isinstance(paths, Path):
        hashtable = get_recursive_hashtable(paths)
        for duplicate_group in iter_duplicate_groups(hashtable):
            deletion_group = get_deletion_group(duplicate_group, *sorting_criteria)
            delete_deletion_group(deletion_group, deletion_method)

    else:
        tmppath = make_temp_symlink_dir(paths)
        try:
            hashtable = get_recursive_hashtable(tmppath)
            for duplicate_group in iter_duplicate_groups(hashtable):
                deletion_group = get_deletion_group(duplicate_group, *sorting_criteria)
                delete_deletion_group(deletion_group, deletion_method)
        finally:
            delete_temp_symlink_dir(tmppath)
