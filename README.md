<h1>Welcome to duplicate_image_finder</h1>
From a top-level view: this project can be used in other python project to check for and delete duplicate images. It is not a standalone program.


<h2>How does this project stand out?</h2>

* It is generally built as a dependency rather than a standalone program. This makes it useful for cleaning up in e.g. file scrapers, which can potentially download a ton of duplicate data.
* It stores the image hashes in seperate files, so that, once generated, the hashes don't need to be generated again.
* Allows for archiving of files, which will load and consider these hashes without the files needing to be present. Saves on disk space.
* I built it how i wanted it, that's the only reason it exists.

<h2>How to install?</h2>
First, head over to the [latest release](https://github.com/TheTimebreaker/duplicate_image_finder/releases/latest) and locate the wheel (`.whl`) file. Copy the url that leads to the file.

* pip: run `pip install url/to/wheel`
* pip + requirements.txt: paste `duplicate_image_finder @ url/to/wheel` in the requirements file
* pyproject.toml: paste `duplicate_image_finder @ url/to/wheel` into \[project\]/dependencies

---

While the entire module structure is exposed for imports, it is recommended to use the functions located in the `main.py` file.