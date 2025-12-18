import os

IGNORE_FOLDERS = {"venv", "env", ".venv", "node_modules", "__pycache__", ".git"}

def tree(dir_path, prefix=""):
    try:
        files = sorted(os.listdir(dir_path))
    except PermissionError:
        return

    # Filter ignored folders
    files = [f for f in files if f not in IGNORE_FOLDERS]

    total = len(files)
    
    for index, file in enumerate(files):
        path = os.path.join(dir_path, file)
        connector = "└── " if index == total - 1 else "├── "
        print(prefix + connector + file)
        
        if os.path.isdir(path):
            extension = "    " if index == total - 1 else "│   "
            tree(path, prefix + extension)

root_dir = "."  # change if needed
tree(root_dir)
