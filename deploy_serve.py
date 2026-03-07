#!/usr/bin/env python3
"""Serve-node deployment for Karaoke — backend only, no frontend.

Deploys the Karaoke backend in SERVE_MODE as a single systemd unit on a
remote host via SSH.  No Next.js frontend is installed or started — serve
nodes exist purely to stream pre-generated content to native clients
(Android TV, iPhone).

The target host must have the deploy user and sudoers configured — see
workflows/deployment/designs/systemd_deployment.md.

Usage:
  SSH_HOST=media.local python deploy_serve.py
  SSH_HOST=media.local DEPLOY_DIR=/opt/karaoke-serve python deploy_serve.py
  SSH_HOST=media.local SSH_USER=deploy SSH_KEY=~/.ssh/id_ed25519 python deploy_serve.py

Environment variables:
  SSH_HOST        Remote host (required)
  SSH_USER        SSH username (default: current local user)
  SSH_KEY         SSH private key path (default: auto-discovered by paramiko)
  SSH_PORT        SSH port (default: 22)
  SERVICE_USER    OS user the service runs as (default: tom)
  DEPLOY_DIR      Deploy directory on remote host (default: /opt/karaoke-serve)
  AI_DEV_PATH     Path to ai-dev repo on remote host (default: ~/ai-dev)
  BACKEND_PORT    Backend port (default: 8001)
"""

import os
import shlex
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_DEV_PATH_LOCAL = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))

sys.path.insert(0, os.path.join(AI_DEV_PATH_LOCAL, "workflows/deployment/src"))

from deploy_lib import SSHTarget  # noqa: E402
from deploy_lib.systemd import (  # noqa: E402
  SystemdConfig,
  SystemdDeployer,
  render_backend_unit,
  step_banner,
  step_create_deploy_dir,
  step_create_dirs,
  step_git_pull,
  step_migrate_data,
  step_reload_daemon,
  step_set_env_permissions,
  step_setup_venv,
  step_write_env,
)
from deploy_lib.target import Target  # noqa: E402

ssh_host = os.environ.get("SSH_HOST")
if not ssh_host:
  print("ERROR: SSH_HOST environment variable is required.")
  print("  Example: SSH_HOST=media.local python deploy_serve.py")
  sys.exit(1)

backend_port = int(os.environ.get("BACKEND_PORT", "8001"))
deploy_dir = os.environ.get("DEPLOY_DIR", "/opt/karaoke-serve")
ai_dev_path = os.environ.get("AI_DEV_PATH", "/opt/ai-dev")


def step_install_backend_unit(target: Target, config: SystemdConfig) -> None:
  """Install only the backend systemd unit (no frontend)."""
  print("Installing systemd unit file...")
  content = render_backend_unit(config)
  path = f"/etc/systemd/system/{config.backend_service}"
  target.run(f"printf '%s' {shlex.quote(content)} | sudo tee {path} > /dev/null")
  print(f"  Installed {path}")


def step_enable_backend(target: Target, config: SystemdConfig) -> None:
  target.run(f"sudo systemctl enable {config.backend_service}")


def step_restart_backend(target: Target, config: SystemdConfig) -> None:
  target.run(f"sudo systemctl restart {config.backend_service}")


def step_serve_summary(target: Target, config: SystemdConfig) -> None:
  svc = config.backend_service
  print()
  print("=" * 42)
  print("Deploy complete!")
  print("=" * 42)
  print()
  print(f"  Deploy dir:  {config.deploy_dir}")
  print(f"  Serve mode:  SERVE_MODE=1 (admin endpoints disabled)")
  print()
  print("  Manage service:")
  print(f"    sudo systemctl start   {svc}")
  print(f"    sudo systemctl stop    {svc}")
  print(f"    sudo systemctl restart {svc}")
  print(f"    sudo systemctl status  {svc}")
  print()
  print("  View logs:")
  print(f"    journalctl -u {svc} -f")
  print()


SERVE_STEPS = [
  step_banner,
  step_git_pull,
  step_create_deploy_dir,
  step_create_dirs,
  step_setup_venv,
  step_migrate_data,
  step_write_env,
  step_set_env_permissions,
  step_install_backend_unit,
  step_reload_daemon,
  step_enable_backend,
  step_restart_backend,
  step_serve_summary,
]

config = SystemdConfig(
  app_name="karaoke",
  project_subpath="frontends/karaoke",
  deploy_dir=deploy_dir,
  ai_dev_path=ai_dev_path,
  backend_port=backend_port,
  frontend_port=3002,  # unused — no frontend deployed
  service_user=os.environ.get("SERVICE_USER", "tom"),
  extra_env_vars={
    "PORT": str(backend_port),
    "SERVE_MODE": "1",
  },
  migrate_data_from="data",
)

_ssh_key = os.environ.get("SSH_KEY")
target = SSHTarget(
  ssh_host,
  user=os.environ.get("SSH_USER"),
  key_filename=os.path.expanduser(_ssh_key) if _ssh_key else None,
  port=int(os.environ.get("SSH_PORT", "22")),
)

SystemdDeployer(config, target, steps=SERVE_STEPS).deploy()
