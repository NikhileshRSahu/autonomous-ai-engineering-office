# Optional Electron shell

The Python `office ui` command remains the supported dependency-light control room. This folder is an optional native desktop shell for users who want a dedicated app window.

## Development run

1. Install the Python package so `office` is on `PATH`.
2. `cd desktop && npm install`
3. `OFFICE_PROJECT=/absolute/path/to/project npm start`

The shell spawns `office ui ... --no-open` on `127.0.0.1`, waits for `/api/health`, and loads only that loopback origin. Renderer Node integration is disabled and context isolation/sandboxing are enabled.

Set `OFFICE_BIN` if the `office` executable is not on `PATH`, and `OFFICE_UI_PORT` to use a different local port.
