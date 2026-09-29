from __future__ import annotations

import json
import subprocess
from pathlib import Path

DESKTOP = Path("desktop")


def test_electron_shell_is_optional_and_local_only():
    package = json.loads((DESKTOP / "package.json").read_text())
    assert package["main"] == "main.js"
    assert "electron" in package["devDependencies"]
    source = (DESKTOP / "main.js").read_text()
    assert "127.0.0.1" in source
    assert "--no-open" in source
    assert "nodeIntegration: false" in source
    assert "contextIsolation: true" in source
    assert "sandbox: true" in source
    assert "child.kill" in source
    assert "https://" not in source
    assert "openExternal" not in source


def test_desktop_js_parses_with_node():
    for path in [DESKTOP / "main.js", DESKTOP / "preload.js"]:
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_desktop_preload_exposes_only_narrow_intake_pickers():
    preload = (DESKTOP / "preload.js").read_text()
    main = (DESKTOP / "main.js").read_text()
    for method in ["chooseProjectFolder", "chooseFiles", "chooseArchive"]:
        assert method in preload
    assert "ipcRenderer.invoke" in preload
    for channel in ["office:choose-project-folder", "office:choose-files", "office:choose-archive"]:
        assert channel in preload
        assert channel in main
    assert "ipcMain.handle" in main
    assert "dialog.showOpenDialog" in main
    assert "openDirectory" in main
    assert "multiSelections" in main
    assert "nodeIntegration: false" in main
    assert "contextIsolation: true" in main
    assert "sandbox: true" in main
