# CHANGELOG

### v1.5.0 - API improvements

- improved app API methods by adding callbacks
- added `lang.txt`.
- moved media plugin into a core plugin directory.
- deleted `history.json`.
- modified the way config files are created. Now they are managed with `api.app` and `app.get_config()`, `app.update_config()`.
- moved gpt model to plugins as `__no_command_callback__` was added.
- deleted `plugins/importer.py` as it was moved mostly to utils.
- removed `lang` variable from inside implementation and moved it to `app.lang` in api. Might be moved to constants in the future.


### v1.4.0

- Created a basis for plugin system
- Created plugin loader utils `plugins/importer.py`
- Created a basis for API for main App
- Renamed some directories and minor fixes


### v1.3.3

- Added `logging_disable` and `logging_enable` functions, broke down `logging_setup` into parts.
- Refactored language-specific utilities and created a `utils/lang` directory
  for python files. (`utils/lang/en.py` instead of `utils/en/text.py`)
- Refactored pre-init and post-init procedures in `app.py` 

### v1.3.2

- Fixed import inconsistency of language-specific utils
- Added music playing by name in media plugin with **YouTube Music**
- Replaced `pygame.mixer` module with `python-vlc` for audio streaming
- Fixed a bug in `data_tree.py` where synonyms for different commands would mix, interrupting a find of actions for a command. 
  For example, command was **disable free speech mode**, but in the command **[mute, volume]**, a word **disable** was set a synonym of mute.
  When expanding synonyms, **disable** in **disable free speech mode** would be replaced with **mute**
  That caused wrong interpretation, and now synonyms are tied to a command where they were stated
- Added a ground up for API, starting with data_tree. 
- Returned `CHANGELOG.md` to a development branch
- Created `data/music` folder for music files downloaded by **YouTube Music**

### v1.3.0

- Using speaker diarization with a vosk SPK model to recognize a speaker, and comparing him with a use of cosine distance 
- Created development branch

### v1.2.5

- Replaced all `os.path.dirname()` with `pathlib.Path`
- Added `version.txt`
- Removed redundant config parameters `include` (reserved)
- Added volume changing function (in progress)

### v1.2.2
- Added data collection for Named Entity Recognition model development 
- Added a script for automatic GPT generation of example requests
- Created a script to count a number of lines of code for `REAMDE.md`
- Moved `data/dev` to `/dev`
- Moved `data/scripts` to `/scripts`
