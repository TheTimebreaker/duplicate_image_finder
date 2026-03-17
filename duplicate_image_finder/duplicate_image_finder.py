"""..."""  # TODO

import logging
import os
import shutil
import time
import traceback
from collections.abc import Generator
from pathlib import Path
from typing import Literal, Optional

import alinas_utils as alut
import imagehash
import imagesize
from pandas import DataFrame
from PIL import Image, ImageFile, UnidentifiedImageError
from send2trash import send2trash

from . import base64custom

Image.MAX_IMAGE_PIXELS = None
Image.warnings.simplefilter("ignore", Image.DecompressionBombWarning)
ImageFile.LOAD_TRUNCATED_IMAGES = True


class Hashfile:
    """Main class that contains hashes of files of specified folder.
    Will load existing hashes, generate missing ones and write those to disk.
        path: Full path to directory
    """

    def __init__(self, path: Path, ignore_hashfiles: bool = False):
        self.path = path
        self.noprint = True
        self.basename = "!hashes"
        self.ext = ".csv"
        self.other_hashfilepaths: list[str] = []
        self.hashpath = self.path / (self.basename + self.ext)

        self.data: dict[str, str | tuple | list] = {}
        self.hashfile_changes = False
        if not ignore_hashfiles:
            self._read_hashes()
        self._generate_hashes()

    def _remove_other_hashfiles(self) -> None:
        for p in self.other_hashfilepaths:
            send2trash(p)

    def _read_single_hashfile(self, file: str) -> Generator[tuple[str, str]] | Generator[tuple[str, str, int, int, int]]:
        with open(file, encoding="utf-8-sig") as f:
            for line in f.read().split("\n"):
                values = line.split(",")
                try:
                    filename, filehash = values
                    yield filename, filehash
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
        allfiles_filenames = {}
        hashfiles: list[tuple[str, str]] = []
        with os.scandir(self.path) as directory:
            for file in directory:
                if not file.is_file():
                    continue
                if self.basename in file.name and self.ext in file.name and not file.name.endswith(".bak"):
                    hashfiles.append((file.path, file.name))
                else:
                    allfiles_filenames[file.name] = True

        for hashfile_path, hashfile_name in hashfiles:
            for elements in self._read_single_hashfile(hashfile_path):
                filepath, filehash = elements[0], elements[1]
                if not self.file_for_hash_exists(filepath, allfiles_filenames):
                    self.hashfile_changes = True
                elif filepath in self.data:  # removes conflicting hashes
                    if self.data[filepath] != filehash:
                        self.data.pop(filepath)
                else:
                    self.data[filepath] = elements[1:]

            if hashfile_name != self.basename + self.ext:
                self.other_hashfilepaths.append(hashfile_path)

        self._write_hashes()
        self._remove_other_hashfiles()

    def file_for_hash_exists(self, filepath: str, allfiles: dict) -> bool:
        return filepath in allfiles

    def _write_hashes(self) -> bool:
        if self.hashfile_changes is False:
            return True
        lines_table = [[filename] + list(map(str, table)) for filename, table in self.data.items()]
        lines_strings = [f"{','.join(line)}" for line in lines_table]
        content_string = "\n".join(lines_strings)
        alut.secureWriteToFile(directory=self.hashpath, content=content_string, encoding="utf-8-sig")
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
                        self.data[file.name] = [global_gethash(filepath)]
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

    def get_fullpath_image(self, filename: str) -> str:
        return os.path.join(self.path, filename)

    def fullpath_key_value(self) -> dict[str, list]:  # ORIGINAL VERSION
        """Returns dictionary with key: hash and value: fullpath to file."""
        result: dict[str, list] = {}
        for filename, elements in self.data.items():
            filehash = elements[0]
            if filehash in result:
                result[filehash].append(self.get_fullpath_image(filename))
            else:
                result[filehash] = [self.get_fullpath_image(filename)]
        return result

    # def fullpathKeyValue(self) -> dict[str, list]: v-A
    #     '''Returns dictionary with key: hash and value: fullpath to file.'''
    #     result:dict[str, list] = {}
    #     for filename, elements in self.data.items():
    #         hash = elements[0]
    #         result.setdefault(hash, []).append(self.get_fullpath_image(filename))
    #     return result


class ArchiveHashfile(Hashfile):
    """Main class that loads archive hashes of specified folder.
    path: Full path to directory
    """

    def __init__(self, path: str | Path) -> None:
        self.folder = path
        self.noprint = False
        self.basename = "!archival-hashes"
        self.ext = ".csv"
        self.hashpath = os.path.join(self.folder, self.basename + self.ext)
        self.data: dict[str, str | tuple | list] = {}
        self.other_hashfilepaths: list[str] = []
        self.hashfile_changes = False
        self._read_hashes()

    def set_data(self, new_data: dict[str, str | tuple | list]) -> None:
        self.data = new_data
        self._write_hashes()

    def get_fullpath_image(self, filename: str) -> str:
        return os.path.join(self.folder, f"archiveHash_{filename}")

    def file_for_hash_exists(self, filepath: str, allfiles: dict) -> Literal[True]:
        return True

    def archive_folder(self, delete_source: bool = False) -> None:
        def remove_files(files: list) -> None:
            for file in files:
                try:
                    os.remove(file)
                    time.sleep(0.01)
                except FileNotFoundError:
                    continue

        hashes = Hashfile(self.folder)
        rm_files = []
        self.hashfile_changes = True
        for i, filepath in enumerate(alut.listallfiles_GENERATOR(self.folder)):
            logging.info(filepath)
            if not self.noprint:
                print(
                    f"\rGenerating archive hashes, dimensions and filesize (#{i})... ",
                    end="",
                )
            if not is_image(filepath):
                continue

            filename = f"{alut.id_generator(6)}.png"  # Rerolls in case of duplicate name :/
            while filename in self.data.keys():
                filename = f"{alut.id_generator(6)}.png"

            filehash = hashes.data[os.path.split(filepath)[-1]]  # Gets the data needed
            if any(isinstance(filehash, instance) for instance in (list, tuple)):
                filehash = filehash[0]
            try:
                width, height = imagesize.get(filepath)
                filesize = os.path.getsize(filepath)
                self.data[filename] = [filehash, int(height), int(width), filesize]
            except UnidentifiedImageError, OSError:
                logging.error("Error encountered that prevents hashing. Moved to */Duplicate image finder/errors .")
                shutil.move(
                    filepath,
                    r"G:\Documents\Visual Studio Code projects\Duplicate image finder\errors",
                )

            rm_files.append(filepath)

        self._write_hashes()
        rm_files.append(os.path.join(self.folder, "!hashes.csv"))

        if delete_source:
            if not self.noprint:
                print("Deleting files... ", end="")
            remove_files(rm_files)

        if not self.noprint:
            print("ALL DONE!")

    # def splitarchives(self, deleteSource:bool = False, length:int = 50000) -> None:
    # doesnt seem to work correctly from reading it, so ill leave that to future me
    #     split_data:dict[int, dict] = {}
    #     split_data_iter = 0
    #     split_data[split_data_iter] = {}
    #     for key, value in self.data.items():
    #         split_data[split_data_iter][key] = value
    #         if len(split_data[split_data_iter]) >= length:
    #             split_data_iter += 1
    #             split_data[split_data_iter] = {}

    #     for i, data in split_data.items():
    #         small = False
    #         if not len(data) >= length:
    #             small = True
    #         temp_folder = os.path.join(self.folder, f"{small*'!small-'}{alut.id_generator(8)}")
    #         while os.path.isdir(temp_folder):
    #             temp_folder = os.path.join(self.folder, f"{small*'!small-'}{alut.id_generator(8)}")

    #         alut.makedirs(temp_folder)
    #         arch = ArchiveHashfile(temp_folder)
    #         arch.set_data(data)

    #     if deleteSource:
    #         alut.rm2bin(self.hashpath)

    def remove_entry(self, filename: str) -> None:
        if filename in self.data.keys():
            self.data.pop(filename)
            self.hashfile_changes = True
        self._write_hashes()


def is_image(file: str) -> bool:
    ext = alut.matchExtension(file)
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


def global_gethash(file: str) -> str:
    return str(
        base64custom.Base64(
            int(
                str(imagehash.phash(Image.open(file), hash_size=16, highfreq_factor=8)),
                16,
            )
        )
    )


def all_subdirs(rootdir: str) -> Generator[str, None, None]:
    yield rootdir
    for root, dirs, _ in os.walk(rootdir, followlinks=True):
        for subdir in dirs:
            yield os.path.join(root, subdir)


def gethashtable(path: str, noprint: bool = False) -> dict[str, list]:
    """Loads/Generates the hashtable."""
    if not noprint:
        print(f"Loading hashes from {path}... ", end="")
    all_hashes: list[dict[str, list]] = []
    for directory in all_subdirs(path):
        ###################################################
        ### LOADS FILEHASHES FOR ALL FILES IN DIRECTORY ###
        ###################################################
        hashes = Hashfile(path=directory)
        all_hashes.append(hashes.fullpath_key_value())

        ###################################################
        ### LOADS ARCHIVAL HASHES #########################
        ###################################################
        archive = ArchiveHashfile(path=directory)
        all_hashes.append(archive.fullpath_key_value())

    if not noprint:
        print("DONE!")
    return alut.combineDictOfLists(*all_hashes)


def getdupegroups(dirhashes: list[dict] | dict, noprint: bool = False) -> list:
    if not noprint:
        print("Getting dupegroups... ", end="")
    if isinstance(dirhashes, list):
        combined: dict[str, list] = {}
        for dirhash in dirhashes:
            combined = alut.combineDictOfLists(combined, dirhash)
    elif isinstance(dirhashes, dict):
        combined = dirhashes

    dupe_groups_table = []
    for files in combined.values():
        if len(files) > 1:
            dupe_groups_table.append([[path] for path in files])

    if not noprint:
        print("DONE! ")
    return dupe_groups_table


def delgroups(
    dupegroups: list[str],
    rm_method: Literal["rm", "recycle"] = "recycle",
    noprint: bool = False,
) -> None:
    """Deletes the duplicate files. rm_method = (rm|<default: recycle>)"""

    def remove_group(
        group: list[tuple[str, int, str, int, Optional[ArchiveHashfile]]],
    ) -> None:
        for i, (file, _, _, _, archive_hashfile_object) in enumerate(group):
            is_first_file = i == 0
            if is_first_file:
                pass
            elif str(os.path.split(file)[1]).startswith("archiveHash_"):
                hashfilekey = str(os.path.split(file)[1]).replace("archiveHash_", "")
                assert archive_hashfile_object
                archive_hashfile_object.remove_entry(hashfilekey)
            else:
                if rm_method == "rm":
                    os.remove(file)
                elif rm_method == "recycle":
                    send2trash(file)

    length_counter = len(dupegroups)
    if length_counter == 0:
        if not noprint:
            print("No files to delete!")
        return

    for i, group in enumerate(dupegroups):
        if not noprint:
            print(f"Deleting #{i+1} / {length_counter} groups... ", end="\r")
        temp: list[tuple[str, int, str, int, Optional[ArchiveHashfile]]] = []
        for file in group:
            try:
                width, height = imagesize.get(file[0])
                dimension = int(width * height)
                temp.append((file[0], dimension, "file", os.path.getsize(file[0]), None))
            except FileNotFoundError:
                try:
                    if str(os.path.basename(file[0])).startswith("archiveHash_"):
                        this_dir, this_file = os.path.split(file[0])
                        assert isinstance(this_dir, str) and isinstance(this_file, str)
                        archive = ArchiveHashfile(path=this_dir)

                        elements = archive.data[this_file.replace("archiveHash_", "")]
                        assert not isinstance(elements, str)
                        _, pixel_height, pixel_length, size = elements
                        temp.append(
                            (
                                file[0],
                                pixel_height * pixel_length,
                                "archive",
                                size,
                                archive,
                            )
                        )
                except KeyError:
                    logging.error("DIF: KeyError for file %s in Archive %s .", this_file, this_dir)

            except UnidentifiedImageError, ValueError:
                logging.error(
                    "UnidentifiedImageError or ValueError: Cannot identify file %s. Moved to */Duplicate image finder/errors .",
                    file[0],
                )
                shutil.move(
                    file[0],
                    r"G:\Documents\Visual Studio Code projects\Downloader\!error_files",
                )

        # sort_order = ["pixel", "archive or not", "filesize"]
        ## 1 pixel: Prefer keeping files with higher pixel counts (generally files with higher height*width)
        ## 2 archive: Keep archives over normal files
        ## 3 filesize: Prefer keeping files with higher filesize (generally compressed files with higher quality)
        if temp:
            df = DataFrame(
                temp,
                columns=[
                    "filename",
                    "pixelcount",
                    "type",
                    "filesize",
                    "archive_object",
                ],
            )
            df.sort_values(
                ["pixelcount", "type", "filesize"],
                ascending=(False, True, False),
                inplace=True,
            )
            temp = df.values.tolist()
            remove_group(group=temp)

    if not noprint:
        print(f"Deleting files from {length_counter} groups... DONE!")


if __name__ == "__main__":
    pass
