import os
from pathlib import Path
from importlib import import_module

from utils import import_modules_from_directory
from api import app  # Import the global AppAPI instance

from data.constants import PROJECT_FOLDER
# List to store dynamically imported plugins
loaded_plugins = []


def find_plugins(directory):
    """
    Find all plugin directories under the main plugin folder.
    """
    skip_dirs = ["__pycache__"]
    subdirectories = []
    base_directory = Path(directory)  # Convert to Path object

    for path in base_directory.rglob('*'):
        if path.is_dir() and path.name not in skip_dirs:
            # Append the relative path to the base directory
            subdirectories.append(str(path.relative_to(Path(PROJECT_FOLDER))))

    return subdirectories


# Import plugins dynamically from each plugin directory
def import_plugins(directory):
    for plugin_dir in directory:
        # Import all modules from the plugin directory
        modules = import_modules_from_directory(plugin_dir)

        # Store the imported modules (plugins)
        loaded_plugins.extend(modules)

