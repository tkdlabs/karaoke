# Bug 02: Stem separation fails with "No such file or directory: 'demucs'" after deploy

## Status
Fixed

## Symptom
POST /api/songs/{id}/stems returns 200 but the background worker immediately fails:
```
Stems failed for {id}: [Errno 2] No such file or directory: 'demucs'
```

## Root Cause
`demucs.py` called the `demucs` CLI as a bare command name (`["demucs", ...]`).
The deployment `start.sh` launches the backend with `nohup .venv/bin/python main.py`
— it does NOT activate the venv, so the venv's `bin/` directory is NOT in `PATH`
for child subprocesses spawned by the server.

Previously the server was started with the venv activated (old `start.sh` in the
repo used `source .venv/bin/activate`), which put the venv's bin in PATH.
The deploy-script-generated `start.sh` removed that activation step, breaking the
subprocess lookup.

## Fix
Replace `"demucs"` with `sys.executable, "-m", "demucs"` in `run_demucs()`.
This always resolves to the same Python environment the server is running under,
regardless of PATH or venv activation state.

## Affected file
`server/demucs.py` — `run_demucs()` function
