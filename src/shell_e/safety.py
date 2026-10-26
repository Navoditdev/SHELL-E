from pathlib import Path


def workspace_path(root: Path, cwd: Path, path: str) -> Path:
    target = (cwd / path).resolve(strict=True)
    if not target.is_relative_to(root):
        raise ValueError("Path is outside the workspace")
    return target


def workspace_directory(root: Path, cwd: Path, path: str) -> Path:
    target = workspace_path(root, cwd, path)
    if not target.is_dir():
        raise ValueError("Not a directory")
    return target
