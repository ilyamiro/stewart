# CHANGELOG

#### v1.9.0

- Created a directory `vectors` and separated speaker recognition into different languages
- Fixed a problem with paths that arose when moving `combine_spk_vectors.py` and `create_spk_sig.py` from `stewart/dev` to `stewart/scripts` directory
- Added fixed `LANG` parameter for creating a speaker signature for russian language.
- Added two new gestures in `custom/gestures` plugin: swipe to the right, swipe to the left between two monitors.
- Created a new plugin management system in the `app/api`.
- Created an experiment translation service for easier localization of plugins.
- Added manifest.yaml file to each plugin for declarative naming and localization.
- Moved `import_plugins` and `find_plugins` from `utils` to `api/app`.
- Created 2 new classes `LocaleService` and `Locale`.
- Separated `api` folder into `commands`, `events`, `locals`.
- Modified some utils like `numbers_to_strings` to better match the current loading language and avoid conflicts.
- Divided plugins into `actions` and `locales`.
- Prevent importing plugins that didn't declare current language as a locale.
- A lot of other small fixes

#### v1.8.2

- Fixed `tts: false` flag for commands `tell_time`, `tell_day` and `tell_month`.
- Added `close/open tab`, `pause video`, `next/previous video` commands for both `ru` and `en` configs.
- Translated `auto_commit.py` into russian due to targeting russian-speaking audience.
- Added support for russian language in `weather`, `gestures`, `taskwarrior`, `battery_health`, `events` plugins.
- Added `translate_commit.py` file to automatically translate commit messages into russian when using `auto-commit`.
- Renamed `FOLDER` to `DIR` in some constants, such as `PROJECT_FOLDER`.
- Added a `None` checker for `class Timeline` when creating a `Scenario`.
- Added a russian translation for different functions in plugin actions like `music` or `core`.
- Removed some actions from the russian config due to incompatibility.

#### v1.8.1

- Fixed a problem with spelling `телеграмм` in russian config
- Removed `pyautogui` dependency, completely replacing it with `pynput` library, directly using `app.Keyboard` from API
- Reworked `hotkey` and `key` actions in `plugins/core/actions/core.py` for usage of `pynput`

#### v1.8.0

- Added `battery` and 'battery health check' functions for my laptop
- Fixed `m/s` being mispronounced by tts in `/plugins/custom/weather.py` by replacing it with `meter per second`
- Relocated config files into a separate directory, removed language filtering for faster loading process.
- Modified how configs are processed in `api/app.py`
- Added russian language commands (translation)
- Fixed sleep mode issues
- Add `timer` and `stopwatch` actions
- Moved 2 scripts from `/dev` > `/scripts/py` and deleted the `/dev` directory
- Modified some scripts (`auto_commit`)
- Added russian language for GPT plugin
- Fixed TTS issues in `weather` plugin
- Modified `say` function in TTS to be able to synthesize without playing and specify the speaker for the model
- Fixed broken `protocol` action in `app/app.py`
- Some other minor improvements

#### v1.7.5 - Small improvements and animation

- Create a terminal "gui" animation out of terminal symbols
- Added weather commands
- Added `fetch_weather` to utils
- Modified GPT prompt 
- Small fixes for `api` and `voice recognition`

#### v1.7.4 - Event system and refinements

- Created a `api/events.py` endpoint for better event registering. Made for ChatGPT inference
- Adjusted Scenario system to the new events endpoint
- More fixes to the command search system. Now the priority is given to the longest detected commands.
- Completely reworked VAD (Voice activity detection system). Added features such as "sleep mode" and heavily modified text-mode usage.
- Other small fixes

#### v1.7.3 - Small improvements and custom commands

- Renamed some API variables
- Added custom commands for personal usage to remote repository `plugins/custom/*`
- Modified some utils for proper functionality
- Improved command search system even further
- Modified scenario system to have triggers include `equivalents` and `synonyms`, just as commands
- Moved scenarios to API instead of utils

#### v1.7.2 - Command search improvements

1. Added some improvements to the command search system
- Now the commands can end the same way some other command starts and overlapping will not occur
2. Added `tell_time`, `tell_day`, `tell_month` actions
3. Moved `play_startup` function to the plugin `core` and added it as a pre-init hook in the api
4. Minor bug fixes in the `app/app.py` implementation of adding commands to the `api.manager`.
- Avoided using tuples and switched to lists completely for commands, since commands are not used as dict keys anymore.

#### v1.7.1 - Scenario system and major improvements

1. Reworked the tree system completely
    1.1. Now commands are not in the tree view, but rather separate objects
    1.2. New context identifier makes it easy to extract specific values in commands.
    1.3. Now commands can separately have a "continues" flag that is useful for search or music requests, instead of hard-coding them
    1.4. Modified all actions to match the new system, since `command` and `context` instances are now separate in **kwargs
    1.5. Completely
2. GUI removal for the time being
    2.1. GUI switch option removed in the main file
3. Removed `__command_processor__` field in the API

#### v1.7.0 - Scenario system and major improvements

- Created a scenario system
- Removed GUI support for the time being (it will be the last thing to implement)
- Changed plugins and reformatted utils

#### v1.6.1 - scripts update and overall improvements. Configuration changes

- Update `auto_commit.py` and `changelog.py` scripts for development
- Fully rework configuration files.
- Remove custom plugins from repository
- Removed `/tree` directory to replace with `/api/tree.py`
- modified GUI and made a parameter in `main` function to start GUI or not
- Lots of minor improvements

Major updates coming in soon!

#### v1.6.0 - User interface added. Android device connection via ADB; Logging improvements;

- Added `check_adb.sh` and `connect_adb.sh` in `scripts/bash/` directory for connection with android phone via wifi
- Made GUI run with app at same time. EXPERIMENTAL!
- Updated utils using 'plyer' module
- Divided `gui` directory into components
- Dirty code, improvements coming


#### v1.5.3 - Stream audio and dir improvements

- Arranged plugin search modules into `actions` as in `core/actions/core.py` or `core/actions/media.py`
- added `stream` function into `core/actions/media.py` to stream audio from url using `mpv`
- improved `stop_audio` action by adding mpv to it.
- added `handle_simple` way of processing commands which is 2 times faster, but works in much more simpler way
- added `add_dir_for_search` function in app api to add all python files in a directory into a search path for commands
- added `include_private` boolean parameter for `add_dir_for_search` and `add_module_for_search` api functions.
  Includes functions that start with `__` or does not.
- Replaced direct ttsi (text-to-speech-instance) import from audio directory in plugins: instead using `api.app.say`.
- Added calendar module into core plugin that helps get events from `.ics` file (gnome-calendar)

#### v1.5.2 - Data tree command processing improvements

- `list_usb_devices` action reworked to match 0 devices connected
- added `admin` function to check whether the program is run with admin privileges
- added try-except structure to run plugin hooks `pre_init` and `post_init`.
- United `__run_pre_init_hooks__` and `__run_post_init_hooks__` into `__run_hooks__`

#### v1.5.1 - Data tree command processing improvements

- Made plugin files more structured
- Improved tree api by splitting main `add_commands` method into parts
- Reworked `__process_multi_word__` and sped it up by x4 times.


#### v1.5.0 - API improvements

- improved app API methods by adding callbacks
- added `lang.txt`.
- moved media plugin into a core plugin directory.
- deleted `history.json`.
- modified the way config files are created. Now they are managed with `api.app` and `app.get_config()`, `app.update_config()`.
- moved gpt model to plugins as `__no_command_callback__` was added.
- deleted `plugins/importer.py` as it was moved mostly to utils.
- removed `lang` variable from inside implementation and moved it to `app.lang` in api. Might be moved to constants in the future.


#### v1.4.0

- Created a basis for plugin system
- Created plugin loader utils `plugins/importer.py`
- Created a basis for API for main App
- Renamed some directories and minor fixes


#### v1.3.3

- Added `logging_disable` and `logging_enable` functions, broke down `logging_setup` into parts.
- Refactored language-specific utilities and created a `utils/lang` directory
  for python files. (`utils/lang/en.py` instead of `utils/en/text.py`)
- Refactored pre-init and post-init procedures in `app.py` 

#### v1.3.2

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

#### v1.3.0

- Using speaker diarization with a vosk SPK model to recognize a speaker, and comparing him with a use of cosine distance 
- Created development branch

#### v1.2.5

- Replaced all `os.path.dirname()` with `pathlib.Path`
- Added `version.txt`
- Removed redundant config parameters `include` (reserved)
- Added volume changing function (in progress)

#### v1.2.2
- Added data collection for Named Entity Recognition model development 
- Added a script for automatic GPT generation of example requests
- Created a script to count a number of lines of code for `REAMDE.md`
- Moved `data/dev` to `/dev`
- Moved `data/scripts` to `/scripts`
