import logging
import time
import traceback
from collections.abc import Generator
from pathlib import Path
from typing import Literal

import imagehash
import imagesize
from PIL import Image, UnidentifiedImageError
from send2trash import send2trash

from .base64custom import Base64
from .utils import Hashtable, atomic_write, id_generator, is_image


def generate_image_hash(file: Path) -> str:
    with Image.open(file) as img:
        return str(
            Base64(
                int(
                    str(imagehash.phash(img, hash_size=16, highfreq_factor=8)),
                    16,
                )
            )
        )


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
        for file in self.path.iterdir():
            if file.name in self.data:  # Skips files that already have a stored hash
                continue

            if "," in file.name:  # Very dumb approach that bypasses CSV issues because commas were in the filename
                new_filepath = self.path.with_name(self.path.name.replace(",", "_"))
                try:
                    file.rename(new_filepath)
                    file = new_filepath
                except FileExistsError:
                    file.unlink()
                    file = new_filepath
            if is_image(file):
                try:
                    self.data[file.name] = (generate_image_hash(file), None, None, None)
                    if self.hashfile_changes is False:
                        self.hashfile_changes = True

                except UnidentifiedImageError, OSError, UserWarning:
                    logging.error("An error occured while generating hash of file %s.", file)

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
