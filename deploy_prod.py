#!/usr/bin/env python3
"""Production (systemd) deployment for Karaoke.

Deploys the Karaoke service as two system-level systemd units on a remote
host via SSH.  The target host must have the deploy user and sudoers
configured — see workflows/deployment/designs/systemd_deployment.md.

Usage:
  SSH_HOST=media.local python deploy_prod.py
  SSH_HOST=media.local SSH_USER=deploy SSH_KEY=~/.ssh/id_ed25519 python deploy_prod.py
  SSH_HOST=media.local SERVE_MODE=1 python deploy_prod.py   # broadcast/serve node

Environment variables:
  SSH_HOST            Remote host (required)
  SSH_USER            SSH username (default: current local user)
  SSH_KEY             SSH private key path (default: auto-discovered by paramiko)
  SSH_PORT            SSH port (default: 22)
  SERVICE_USER        OS user the service runs as (default: tom)
  DEPLOY_DIR          Deploy directory on remote host (default: /opt/karaoke)
  AI_DEV_PATH         Path to ai-dev repo on remote host (default: /opt/ai-dev)
  BACKEND_PORT        Backend port (default: 8001)
  FRONTEND_PORT       Frontend port (default: 3002)
  API_URL             Public URL of the backend API as seen by browser clients
                      (default: http://localhost:BACKEND_PORT).
                      Override when clients connect from other machines, e.g.
                      http://192.168.1.10:8001 or https://karaoke.example.com
  SERVE_MODE          Set to "1" to deploy in read-only serving mode (no yt-dlp /
                      Demucs / admin endpoints).  Requires SERVE_MODE support in
                      server/main.py — see designs/serve_mode.md.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_DEV_PATH_LOCAL = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))

sys.path.insert(0, os.path.join(AI_DEV_PATH_LOCAL, "workflows/deployment/src"))

from deploy_lib import SSHTarget  # noqa: E402
from deploy_lib.systemd import SystemdConfig, SystemdDeployer  # noqa: E402

ssh_host = os.environ.get("SSH_HOST")
if not ssh_host:
  print("ERROR: SSH_HOST environment variable is required.")
  print("  Example: SSH_HOST=media.local python deploy_prod.py")
  sys.exit(1)

backend_port = int(os.environ.get("BACKEND_PORT", "8001"))
frontend_port = int(os.environ.get("FRONTEND_PORT", "3002"))
deploy_dir = os.environ.get("DEPLOY_DIR", "/opt/karaoke")
ai_dev_path = os.environ.get("AI_DEV_PATH", "/opt/ai-dev")
api_url = os.environ.get("API_URL", f"http://localhost:{backend_port}")
serve_mode = os.environ.get("SERVE_MODE", "")

config = SystemdConfig(
  app_name="karaoke",
  project_subpath="frontends/karaoke",
  deploy_dir=deploy_dir,
  ai_dev_path=ai_dev_path,
  backend_port=backend_port,
  frontend_port=frontend_port,
  service_user=os.environ.get("SERVICE_USER", "tom"),
  # PORT must be a literal here — systemd EnvironmentFile= does not expand $VARS.
  # SERVE_MODE written to .env so operators can toggle it without re-deploying.
  extra_env_vars={
    "PORT": str(backend_port),
    "SERVE_MODE": serve_mode,
  },
  # NEXT_PUBLIC_API_URL is baked into the Next.js bundle at build time.
  # Override API_URL when clients connect from other hosts (TVs, phones).
  frontend_env_vars={
    "NEXT_PUBLIC_API_URL": api_url,
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

SystemdDeployer(config, target).deploy()
