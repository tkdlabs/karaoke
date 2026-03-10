# Bug 03: Stem separation silently does nothing — local demucs.py shadows installed package

## Status
Fixed

## Symptom
POST /api/songs/{id}/stems returns 200, background worker reports:
```
Stems failed for {id}: Vocals stem not found at /tmp/tmp.../htdemucs/audio/vocals.mp3
```
No demucs progress output appears in backend.log before the failure.

## Root Cause
`run_demucs()` called `sys.executable -m demucs` to invoke the demucs CLI. Python's
`-m` flag searches `sys.path` for a module named `demucs`. The server directory
(`frontends/karaoke/server/`) is on `sys.path`, and it contains `demucs.py` — our own
local wrapper module. Python finds and runs that file instead of the installed demucs
package. Since `server/demucs.py` has no `__main__` block, `python -m demucs` exits
immediately with code 0 and produces no output.

The bug was introduced when `sys.executable -m demucs` replaced the bare `"demucs"`
command (bug 02 fix), which happened to work around the PATH issue but introduced
this shadowing issue.

## Fix
Call the demucs binary by its full path — `Path(sys.executable).parent / "demucs"` —
which is always co-located with the Python interpreter in the venv. This bypasses
module lookup entirely and invokes the real demucs CLI via its shebang.

Also added `capture_output=True` to the subprocess call so stderr is captured and
included in any RuntimeError on failure, instead of disappearing into the void.

## Affected file
`server/demucs.py` — `run_demucs()` function
