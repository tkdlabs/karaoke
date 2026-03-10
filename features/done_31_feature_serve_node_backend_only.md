# Feature: Serve node deploys backend only (no frontend)

When deploying in serve mode, the Next.js frontend is not useful — it's an
admin UI. The serve node should run the backend only.

## What to do

Add a `deploy_serve.py` script that deploys only the backend (no npm install,
no frontend build, no frontend systemd unit) using `SERVE_MODE=1`.

### New file: `deploy_serve.py`

Use `SystemdDeployer` with a custom steps list that omits `step_install_npm`,
`step_build_frontend`, and the frontend systemd unit from `step_install_units`.

The simplest approach: subclass or pass a custom steps list that replaces
`step_install_units` with a backend-only variant, and drops `step_install_npm`
and `step_build_frontend`.

Look at `SYSTEMD_STEPS` in `workflows/deployment/src/deploy_lib/systemd.py` —
use all steps except `step_install_npm`, `step_build_frontend`, and replace
`step_install_units` with a step that only installs the backend unit.

### Custom step

```python
def step_install_backend_unit(target, config):
    """Install only the backend systemd unit (no frontend)."""
    content = render_backend_unit(config)
    path = f"/etc/systemd/system/{config.backend_service}"
    target.run(f"printf '%s' {shlex.quote(content)} | sudo tee {path} > /dev/null")
    print(f"  Installed {path}")
```

### Custom summary step

Print only backend service management commands (no frontend service).

### `SystemdConfig` for serve node

- `SERVE_MODE=1` in `extra_env_vars`
- `frontend_port` still required by `DeployConfig` — pass the default but it
  won't be used
- No `frontend_env_vars` needed

### Usage

```
SSH_HOST=media.local python deploy_serve.py
SSH_HOST=media.local DEPLOY_DIR=/opt/karaoke-serve python deploy_serve.py
```
