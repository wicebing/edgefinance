from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CodexCommand:
    executable: str
    prefix_arguments: tuple[str, ...] = ()
    source: str = ""

    def argv(self, *arguments: str) -> list[str]:
        return [self.executable, *self.prefix_arguments, *arguments]


def _natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def _existing_file(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(os.path.expandvars(str(value).strip().strip('"'))).expanduser()
    return path.resolve() if path.is_file() else None


def find_codex_command(
    settings: Mapping[str, object] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> CodexCommand | None:
    """Find Codex installed on PATH, by npm, or inside a supported editor.

    VS Code extensions amend PATH only for some terminals. Weekly scripts launched
    from cmd.exe therefore need to discover the extension executable directly.
    """
    values = settings or {}
    env = dict(os.environ if environ is None else environ)
    system = platform_name or sys.platform
    machine = (architecture or platform.machine()).lower()

    override = _existing_file(str(values.get("EDGEFINANCE_CODEX_PATH") or env.get("EDGEFINANCE_CODEX_PATH") or ""))
    if override:
        if override.suffix.lower() == ".js":
            node = shutil.which("node", path=env.get("PATH"))
            if node:
                return CodexCommand(node, (str(override),), "EDGEFINANCE_CODEX_PATH")
        else:
            return CodexCommand(str(override), (), "EDGEFINANCE_CODEX_PATH")

    executable_name = "codex.exe" if system == "win32" else "codex"
    on_path = shutil.which(executable_name, path=env.get("PATH"))
    if on_path:
        return CodexCommand(str(Path(on_path).resolve()), (), "PATH")

    if system != "win32":
        return None

    path_directories = [Path(part) for part in env.get("PATH", "").split(os.pathsep) if part]
    npm_loaders = [
        Path(value) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        for value in [env.get("APPDATA")]
        if value
    ]
    npm_loaders += [
        Path(value) / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        for value in [env.get("NVM_SYMLINK"), env.get("npm_config_prefix"), *path_directories]
        if value
    ]
    node = shutil.which("node.exe", path=env.get("PATH")) or shutil.which("node", path=env.get("PATH"))
    if node:
        for loader in npm_loaders:
            if loader.is_file():
                return CodexCommand(str(Path(node).resolve()), (str(loader.resolve()),), "global npm package")

    home_directory = home or Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    extension_roots = [
        home_directory / ".vscode" / "extensions",
        home_directory / ".vscode-insiders" / "extensions",
        home_directory / ".cursor" / "extensions",
    ]
    architecture_directories = (
        ["windows-arm64", "windows-x86_64"] if machine in {"arm64", "aarch64"}
        else ["windows-x86_64", "windows-arm64"]
    )
    for root in extension_roots:
        try:
            extensions = sorted(
                (path for path in root.iterdir() if path.is_dir() and path.name.lower().startswith("openai.chatgpt-")),
                key=_natural_key,
                reverse=True,
            )
        except OSError:
            continue
        for extension in extensions:
            for architecture_directory in architecture_directories:
                candidate = extension / "bin" / architecture_directory / "codex.exe"
                if candidate.is_file():
                    return CodexCommand(str(candidate.resolve()), (), "OpenAI editor extension")
    return None
