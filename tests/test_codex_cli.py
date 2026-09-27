from pathlib import Path

from edgefinance.codex_cli import find_codex_command


def test_explicit_codex_path_has_priority(tmp_path):
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"fixture")
    command = find_codex_command(
        {"EDGEFINANCE_CODEX_PATH": str(executable)},
        environ={"PATH": ""}, platform_name="win32", home=tmp_path,
    )
    assert command and command.executable == str(executable.resolve())
    assert command.source == "EDGEFINANCE_CODEX_PATH"


def test_vscode_extension_is_found_without_path(tmp_path):
    older = tmp_path / ".vscode/extensions/openai.chatgpt-26.9.900-win32-x64/bin/windows-x86_64/codex.exe"
    newer = tmp_path / ".vscode/extensions/openai.chatgpt-26.10.100-win32-x64/bin/windows-x86_64/codex.exe"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    command = find_codex_command({}, environ={"PATH": "", "USERPROFILE": str(tmp_path)},
        platform_name="win32", architecture="amd64", home=tmp_path)
    assert command and Path(command.executable) == newer.resolve()
    assert command.source == "OpenAI editor extension"
