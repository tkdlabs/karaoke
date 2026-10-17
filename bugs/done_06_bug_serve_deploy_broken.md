# Bug 06: `deploy.py --serve` cannot install a working service

## Status
Fixed

## Symptom
Running `python deploy.py --serve --host <server>` against a fresh checkout fails
before the service ever starts. Three separate failures appear in sequence.

1. Dependency install:

```
RuntimeError: Command failed (exit 1):
  uv pip install --python .../.venv/bin/python3 requirements-serve.txt
  × No solution found when resolving dependencies:
  ╰─▶ Because requirements-serve-txt was not found in the package registry ...
```

2. `daemon-reload` (non-interactive sudo):

```
sudo systemctl daemon-reload karaoke-backend.service
sudo: a terminal is required to read the password ...
sudo: a password is required
```

3. Unit installs, but the backend crashes on startup:

```
RuntimeError: Form data requires "python-multipart" to be installed.
You can install "python-multipart" with:
pip install python-multipart
```

## Root cause
Three independent issues in the serve deploy path:

1. `step_setup_venv()` passed the serve requirements file to `uv` without `-r`
   (`uv pip install ... requirements-serve.txt`). uv therefore treated
   `requirements-serve.txt` as a package spec instead of a requirements file.

2. `step_systemd_cmd()` appended the unit name to *every* subcommand, producing
   the invalid `systemctl daemon-reload karaoke-backend.service`. The extra
   argument also means the command no longer matches the usual
   `NOPASSWD: /bin/systemctl daemon-reload` sudoers rule, so it prompts for a
   password.

3. `requirements-serve.txt` omitted `python-multipart`. In `SERVE_MODE` the admin
   router is not *included*, but the `/api/songs/import` route is still
   *registered* (decorators execute at import time) and uses
   `UploadFile`/`File`/`Form`, so FastAPI raises at import unless
   `python-multipart` is installed.

## Fix
- `deploy.py`: build the install spec as `-r requirements-serve.txt` for the
  serve case (`-e .` is passed through unchanged).
- `deploy.py`: call `systemctl daemon-reload` without a unit argument.
- `server/requirements-serve.txt`: add `python-multipart` (same class of omission
  as the `korean_romanizer` miss in bug 05).

## Affected files
- `deploy.py` — `step_setup_venv()`, `step_systemd_cmd()`
- `server/requirements-serve.txt`
