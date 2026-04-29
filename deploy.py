#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jinja2>=3.1", "fabric>=3.0"]
# ///
"""Deploy Karaoke — full (frontend + backend) or serve-only (backend, systemd).

Usage
-----
Local full deploy:

    python deploy.py

Remote full deploy:

    python deploy.py --host 192.168.0.236
    python deploy.py --host myserver --user tom --key ~/.ssh/id_ed25519

Serve-only deploy (backend only, systemd, no frontend):

    python deploy.py --host 192.168.0.236 --serve
    python deploy.py --host media.local --serve --user deploy

Environment variables (all optional):
  DEPLOY_DIR      Deploy directory (default: ~/deployments/karaoke for full,
                  /opt/karaoke-serve for serve)
  AI_DEV_PATH     ai-dev repo root on target (default: ~/ai-dev, or inferred locally)
  BACKEND_PORT    Backend port (default: 8001)
  FRONTEND_PORT   Frontend port (default: 3002, full mode only)
  FRONTEND_MODE   "dev" or "prod" (default: dev, full mode only)
  SERVICE_USER    OS user the service runs as (default: tom, serve mode only)
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_local_ai_dev = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))

sys.path.insert(0, os.path.join(_local_ai_dev, "workflows/deployment/src"))

from deploy_lib import DeployConfig, Deployer, LocalTarget, SSHTarget, add_no_pull_arg, add_no_service_install_arg, add_recreate_venv_arg  # noqa: E402
from deploy_lib.steps import step_setup_venv  # noqa: E402
from deploy_lib.systemd import (  # noqa: E402
  SYSTEMD_STEPS,
  SystemdConfig,
  SystemdDeployer,
)
from deploy_lib.target import Target  # noqa: E402


def step_setup_venv_serve(target: Target, config: SystemdConfig) -> None:
  """Install backend deps from requirements-serve.txt (no torch/demucs/yt-dlp)."""
  print("Setting up Python venv (serve deps only)...")
  venv = f"{config.deploy_dir}/.venv"
  python = f"{venv}/bin/python3"
  if not target.exists(venv):
    target.run(f"uv venv {venv}")
  target.run(f"uv pip install --python {python} -r requirements-serve.txt", cwd=config.backend_dir)


SERVE_STEPS = [step_setup_venv_serve if s is step_setup_venv else s for s in SYSTEMD_STEPS]


def main() -> None:
  parser = argparse.ArgumentParser(description="Deploy Karaoke")
  parser.add_argument("--host", default=None, help="SSH hostname or IP (omit for local deploy)")
  parser.add_argument("--user", default=None, help="SSH username (default: current user)")
  parser.add_argument(
    "--key",
    default=os.path.expanduser("~/.ssh/id_ed25519"),
    help="Path to SSH private key (default: ~/.ssh/id_ed25519)",
  )
  parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
  add_no_pull_arg(parser)
  add_no_service_install_arg(parser)
  add_recreate_venv_arg(parser)
  mode = parser.add_mutually_exclusive_group(required=True)
  mode.add_argument(
    "--serve",
    action="store_true",
    help="Serve-only mode: backend via systemd, no frontend. Requires --host.",
  )
  mode.add_argument(
    "--full",
    action="store_true",
    help="Full deploy: frontend + backend via nohup.",
  )
  args = parser.parse_args()

  if args.serve and not args.host:
    parser.error("--serve requires --host")

  backend_port = int(os.environ.get("BACKEND_PORT", "8001"))

  if args.serve:
    deploy_dir = os.environ.get("DEPLOY_DIR", "/opt/karaoke-serve")
    ai_dev_path = os.environ.get("AI_DEV_PATH", "/opt/ai-dev")
    config = SystemdConfig(
      app_name="karaoke",
      project_subpath="frontends/karaoke",
      deploy_dir=deploy_dir,
      ai_dev_path=ai_dev_path,
      backend_port=backend_port,
      frontend_port=3002,  # unused — no frontend deployed
      no_frontend=True,
      service_user=os.environ.get("SERVICE_USER", "tom"),
      extra_env_vars={"PORT": str(backend_port), "SERVE_MODE": "1"},
      migrate_data_from="data",
      skip_git_pull=args.no_pull,
      skip_service_install=args.no_service_install,
      recreate_venv=args.recreate_venv,
    )
    target = SSHTarget(args.host, user=args.user, key_filename=args.key, port=args.port)
    SystemdDeployer(config, target, steps=SERVE_STEPS).deploy()
  else:
    if args.host:
      ai_dev_path = os.environ.get("AI_DEV_PATH", "~/ai-dev")
      target = SSHTarget(args.host, user=args.user, key_filename=args.key, port=args.port)
    else:
      ai_dev_path = os.environ.get("AI_DEV_PATH", _local_ai_dev)
      target = LocalTarget()

    deploy_dir = os.environ.get("DEPLOY_DIR", os.path.expanduser("~/deployments/karaoke"))
    config = DeployConfig(
      app_name="Karaoke",
      project_subpath="frontends/karaoke",
      deploy_dir=deploy_dir,
      ai_dev_path=ai_dev_path,
      backend_port=backend_port,
      frontend_port=int(os.environ.get("FRONTEND_PORT", "3002")),
      frontend_mode=os.environ.get("FRONTEND_MODE", "dev"),
      migrate_data_from="data",
      kill_stale_ports=True,
      skip_git_pull=args.no_pull,
      recreate_venv=args.recreate_venv,
    )
    Deployer(config, target).deploy()


if __name__ == "__main__":
  main()
