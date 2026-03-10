# Bug 04: Backend logs have no timestamps and minimal context

## Status
Open

## Symptom
backend.log mixes uvicorn access log lines (which include timestamps via uvicorn's
own formatter) with bare `print()` statements from workers that have no timestamp:
```
INFO:     192.168.0.178:59296 - "POST /api/songs/.../stems HTTP/1.1" 200 OK
Stems failed for abc123: Vocals stem not found at /tmp/...
```
The worker output line has no timestamp, log level, or source context, making it
impossible to correlate failures with request times or measure how long workers ran.

## Impact
- Cannot determine when a failure occurred relative to other events
- Cannot measure worker duration (start vs end timestamps)
- Worker errors look identical to info messages in the log

## Fix
Replace `print()` calls in `server/main.py` (and workers) with Python `logging`
using a formatter that includes timestamps, level, and message. Configure uvicorn
to use the same handler so all output is consistent.

Suggested format: `%(asctime)s [%(levelname)s] %(message)s`
Example: `2026-03-09 22:10:43 [INFO] Stems ready: abc123`
