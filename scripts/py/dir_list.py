import os


def print_directory_tree(root_dir, indent='', exclude_dirs=None):
    # Set default value for exclude_dirs if not provided
    if exclude_dirs is None:
        exclude_dirs = []

    # Get all files and directories in the current directory
    entries = os.listdir(root_dir)

    # Loop through each entry
    for index, entry in enumerate(entries):
        # Determine the full path
        full_path = os.path.join(root_dir, entry)

        # Check if the entry is the last one in the directory
        is_last = index == len(entries) - 1

        # Print the appropriate tree structure symbols

        if entry not in exclude_dirs:
            if is_last:
                print(indent + '└── ' + entry)
                next_indent = indent + '    '  # Add space for the next level of indentation
            else:
                print(indent + '├── ' + entry)
                next_indent = indent + '│   '  # Add vertical line for further entries

        if os.path.isdir(full_path) and entry not in exclude_dirs:
            print_directory_tree(full_path, next_indent, exclude_dirs)


root_directory = '/home/ilyamiro/stewart'

exclude = ['venv', 'models', "__pycache__", ".git", ".idea", "app_log", "sounds", "images", "grammar", "include"]

print_directory_tree(root_directory, exclude_dirs=exclude)
