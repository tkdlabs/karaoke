#!/usr/bin/env python3
"""Deploy Karaoke — full (frontend + backend) or serve-only (backend, systemd).

Self-contained: only the Python standard library is required (no deploy_lib,
no fabric, no jinja2). SSH is used via the system ``ssh``/``scp`` binaries.

Usage
-----
Local full deploy (frontend + backend via generated start.sh/stop.sh):

    python deploy.py --full

Remote full deploy:

    python deploy.py --full --host 192.168.0.236
    python deploy.py --full --host myserver --user tom --key ~/.ssh/id_ed25519

Serve-only deploy (backend via systemd, no frontend; requires --host):

    python deploy.py --serve --host 192.168.0.236
    python deploy.py --serve --host media.local --user deploy

Environment variables (all optional):
  DEPLOY_DIR      Deploy directory on the target (default: ~/deployments/karaoke
                  for full, /opt/karaoke-serve for serve)
  REPO_DIR        Repo checkout path on the target (default: <script dir> for
                  local, ~/karaoke for remote)
  BACKEND_PORT    Backend port (default: 8001)
  FRONTEND_PORT   Frontend port (default: 3002, full mode only)
  FRONTEND_MODE   "dev" or "prod" (default: dev, full mode only)
  SERVICE_USER    OS user the service runs as (default: current user, serve mode)
"""

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UV_INSTALL_CMD = "curl -LsSf https://astral.sh/uv/install.sh | sh"
# Non-interactive SSH sessions don't source ~/.bashrc, so add user bin dirs.
SSH_PATH_PREFIX = "export PATH=\"$HOME/.local/bin:$HOME/.cargo/bin:$PATH\""


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class Config:
  deploy_dir: str
  repo_dir: str
  backend_port: int
  frontend_port: int
  frontend_mode: str = "dev"
  service_user: str = ""
  no_frontend: bool = False
  skip_git_pull: bool = False
  skip_service_install: bool = False
  recreate_venv: bool = False
  backend_startup_sleep: int = 2
  frontend_startup_sleep: int = 3
  kill_stale_ports: bool = False
  restart_delay: int = 5
  start_limit_burst: int = 3
  start_limit_interval: int = 60

  @property
  def backend_dir(self) -> str:
    return f"{self.repo_dir}/server"

  @property
  def frontend_dir(self) -> str:
    return self.repo_dir

  @property
  def service_prefix(self) -> str:
    return "karaoke"


# ── Target abstraction ────────────────────────────────────────────────────────


class Target:
  def run(self, cmd: str, cwd: str | None = None, stdin: str | None = None) -> str:
    raise NotImplementedError

  def put_text(self, content: str, path: str, mode: int = 0o644) -> None:
    raise NotImplementedError

  def exists(self, path: str) -> bool:
    raise NotImplementedError

  def makedirs(self, path: str) -> None:
    raise NotImplementedError

  def listdir(self, path: str) -> list:
    raise NotImplementedError

  def command_exists(self, cmd: str) -> bool:
    raise NotImplementedError

  def is_local(self) -> bool:
    return False


class LocalTarget(Target):
  def run(self, cmd: str, cwd: str | None = None, stdin: str | None = None) -> str:
    result = subprocess.run(
      cmd,
      shell=True,
      input=stdin,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      cwd=cwd,
    )
    if result.returncode != 0:
      raise RuntimeError(
        f"Command failed (exit {result.returncode}):\n  {cmd}\n{result.stdout}"
      )
    return result.stdout

  def put_text(self, content: str, path: str, mode: int = 0o644) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    p.chmod(mode)

  def exists(self, path: str) -> bool:
    return Path(path).expanduser().exists()

  def makedirs(self, path: str) -> None:
    Path(path).expanduser().mkdir(parents=True, exist_ok=True)

  def listdir(self, path: str) -> list:
    p = Path(path).expanduser()
    return os.listdir(p) if p.exists() else []

  def command_exists(self, cmd: str) -> bool:
    import shutil

    return shutil.which(cmd) is not None

  def is_local(self) -> bool:
    return True


class SSHTarget(Target):
  """Run commands over the system ssh binary (no python ssh dependency)."""

  def __init__(
    self,
    host: str,
    user: str | None = None,
    key_filename: str | None = None,
    port: int | None = None,
  ):
    self._base = ["ssh"]
    if key_filename:
      self._base += ["-i", key_filename]
    if port:
      self._base += ["-p", str(port)]
    target = host if not user else f"{user}@{host}"
    self._base.append(target)
    self._target = target

  def run(self, cmd: str, cwd: str | None = None, stdin: str | None = None) -> str:
    if cwd:
      cmd = f"cd {shlex.quote(cwd)} && {cmd}"
    cmd = f"{SSH_PATH_PREFIX} && {cmd}"
    result = subprocess.run(
      self._base + [cmd],
      input=stdin,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
    )
    if result.returncode != 0:
      raise RuntimeError(
        f"Command failed (exit {result.returncode}):\n  {cmd}\n{result.stdout}"
      )
    return result.stdout

  def put_text(self, content: str, path: str, mode: int = 0o644) -> None:
    remote_cmd = f"cat > {shlex.quote(path)}"
    self.run(remote_cmd, stdin=content)
    if mode != 0o644:
      self.run(f"chmod {oct(mode)[2:]} {shlex.quote(path)}")

  def exists(self, path: str) -> bool:
    result = subprocess.run(
      self._base + [f"test -e {shlex.quote(path)}"],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
    )
    return result.returncode == 0

  def makedirs(self, path: str) -> None:
    self.run(f"mkdir -p {shlex.quote(path)}")

  def listdir(self, path: str) -> list:
    out = self.run(f"ls -A {shlex.quote(path)} 2>/dev/null || true")
    return [f for f in out.split("\n") if f]

  def command_exists(self, cmd: str) -> bool:
    result = subprocess.run(
      self._base + [f"{SSH_PATH_PREFIX} && command -v {cmd}"],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
    )
    return result.returncode == 0

  def is_local(self) -> bool:
    return False


# ── Script / unit template rendering ──────────────────────────────────────────


def render_start_sh(cfg: Config) -> str:
  backend_line = "nohup \"$DEPLOY_DIR/.venv/bin/python\" main.py \\"
  frontend_prod = (
    'echo "Building frontend..."\n'
    "npm run build\n"
    "nohup npm run start -- -p \"$FRONTEND_PORT\" \\"
  )
  frontend_dev = "nohup npm run dev -- -p \"$FRONTEND_PORT\" \\"
  frontend_block = ""
  if not cfg.no_frontend:
    frontend_block = f"""
# ── Frontend ─────────────────────────────────────────────────────────────
echo "Starting frontend on port $FRONTEND_PORT (mode: ${{FRONTEND_MODE:-dev}})..."
cd "{cfg.frontend_dir}"
if [ "${{FRONTEND_MODE:-dev}}" = "prod" ]; then
  {frontend_prod}
    > "$DEPLOY_DIR/logs/frontend.log" 2>&1 &
else
  {frontend_dev}
    > "$DEPLOY_DIR/logs/frontend.log" 2>&1 &
fi
FRONTEND_PID=$!
echo $FRONTEND_PID > "$DATA_DIR/frontend.pid"

sleep {cfg.frontend_startup_sleep}
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
  echo "ERROR: Frontend failed to start — see $DEPLOY_DIR/logs/frontend.log"
  tail -20 "$DEPLOY_DIR/logs/frontend.log"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi
echo "Frontend started (PID: $FRONTEND_PID)"
"""
  summary_extra = (
    'echo "  Frontend: http://localhost:${FRONTEND_PORT}"\n' if not cfg.no_frontend else ""
  )
  return f"""#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# Load env
set -a; source "$SCRIPT_DIR/.env"; set +a
# Expand ~ in path vars
REPO_DIR="${{REPO_DIR/#\\~/\\$HOME}}"
DEPLOY_DIR="${{DEPLOY_DIR/#\\~/\\$HOME}}"
DATA_DIR="${{DATA_DIR:-$DEPLOY_DIR/data}}"

mkdir -p "$DEPLOY_DIR/logs" "$DATA_DIR"

# ── Backend ──────────────────────────────────────────────────────────────
echo "Starting backend on port $BACKEND_PORT..."
cd "{cfg.backend_dir}"
{backend_line}
  > "$DEPLOY_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$DATA_DIR/backend.pid"

sleep {cfg.backend_startup_sleep}
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  echo "ERROR: Backend failed to start — see $DEPLOY_DIR/logs/backend.log"
  tail -20 "$DEPLOY_DIR/logs/backend.log"
  exit 1
fi
echo "Backend started (PID: $BACKEND_PID)"
{frontend_block}
echo ""
echo "Karaoke is running!"
{summary_extra}echo "  Backend:  http://localhost:${{BACKEND_PORT}}"
echo "  Logs:     $DEPLOY_DIR/logs/"
echo "  Data:     $DATA_DIR"
echo ""
echo "To stop: $SCRIPT_DIR/stop.sh"
"""


def render_stop_sh(cfg: Config) -> str:
  frontend_stop = "stop_pid frontend\n" if not cfg.no_frontend else ""
  stale_ports = ""
  if cfg.kill_stale_ports:
    stale_ports = f"""
# Kill anything still holding the ports (handles stale processes)
if command -v fuser &>/dev/null; then
  fuser -k "${{BACKEND_PORT}}/tcp" 2>/dev/null && echo "  Killed stale process on port $BACKEND_PORT" || true
  fuser -k "${{FRONTEND_PORT}}/tcp" 2>/dev/null && echo "  Killed stale process on port $FRONTEND_PORT" || true
fi
"""
  return f"""#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
set -a; source "$SCRIPT_DIR/.env"; set +a
DEPLOY_DIR="${{DEPLOY_DIR/#\\~/\\$HOME}}"
DATA_DIR="${{DATA_DIR:-$DEPLOY_DIR/data}}"

echo "Stopping Karaoke..."

stop_pid() {{
  local name="$1"
  local pidfile="$DATA_DIR/${{name}}.pid"
  if [ -f "$pidfile" ]; then
    PID=$(cat "$pidfile")
    if kill -0 "$PID" 2>/dev/null; then
      echo "  Stopping $name (PID: $PID)..."
      kill "$PID"
    else
      echo "  $name PID $PID not found"
    fi
    rm -f "$pidfile"
  fi
}}

stop_pid backend
{frontend_stop}{stale_ports}echo "Done"
"""


def render_backend_unit(cfg: Config) -> str:
  return f"""[Unit]
Description=Karaoke — backend
After=network.target
StartLimitIntervalSec={cfg.start_limit_interval}
StartLimitBurst={cfg.start_limit_burst}

[Service]
Type=simple
User={cfg.service_user}
WorkingDirectory={cfg.backend_dir}
EnvironmentFile={cfg.deploy_dir}/.env
Environment="PORT=${{BACKEND_PORT}}"
ExecStart={cfg.deploy_dir}/.venv/bin/python main.py
Restart=on-failure
RestartSec={cfg.restart_delay}

[Install]
WantedBy=multi-user.target
"""


# ── Shared steps ──────────────────────────────────────────────────────────────


def step_banner(target: Target, cfg: Config) -> None:
  print("=" * 42)
  print("Karaoke — Deploy")
  print("=" * 42)
  print(f"  Deploy dir:  {cfg.deploy_dir}")
  print(f"  Repo dir:    {cfg.repo_dir}")
  print(f"  Backend:     port {cfg.backend_port}")
  if not cfg.no_frontend:
    print(f"  Frontend:    port {cfg.frontend_port} (mode: {cfg.frontend_mode})")
  print()


def step_git_pull(target: Target, cfg: Config) -> None:
  if cfg.skip_git_pull:
    print("Skipping git pull (--no-pull)")
    return
  if not target.is_local():
    print("Updating repository...")
    target.run("git pull --ff-only", cwd=cfg.repo_dir)


def step_create_dirs(target: Target, cfg: Config) -> None:
  print("Creating directories...")
  target.makedirs(f"{cfg.deploy_dir}/data")
  target.makedirs(f"{cfg.deploy_dir}/logs")


def step_ensure_uv(target: Target, cfg: Config) -> None:
  if target.command_exists("uv"):
    return
  print("Installing uv on target...")
  target.run(UV_INSTALL_CMD)


def step_setup_venv(target: Target, cfg: Config) -> None:
  venv = f"{cfg.deploy_dir}/.venv"
  python = f"{venv}/bin/python3"
  if cfg.recreate_venv and target.exists(venv):
    print("  Removing existing venv (--recreate-venv)...")
    target.run(f"rm -rf {venv}")
  if not target.exists(venv):
    print("Setting up Python venv...")
    target.run(f"uv venv {venv}")
  req = "requirements-serve.txt" if cfg.no_frontend else "-e ."
  print("Installing backend deps...")
  target.run(f"uv pip install --python {python} {req}", cwd=cfg.backend_dir)


def step_install_npm(target: Target, cfg: Config) -> None:
  if cfg.no_frontend:
    return
  print("Installing frontend dependencies...")
  target.run("npm install --loglevel=error", cwd=cfg.frontend_dir)


def step_migrate_data(target: Target, cfg: Config) -> None:
  if not target.is_local():
    print("Skipping data migration (not supported for remote targets — use rsync)")
    return
  src = f"{cfg.repo_dir}/data"
  dst = f"{cfg.deploy_dir}/data"
  if not target.exists(src) or not target.listdir(src):
    return
  if target.listdir(dst):
    print("Skipping data migration — deploy data dir already has content")
    return
  print(f"Migrating data: {src} → {dst} ...")
  target.run(f"cp -r {src}/. {dst}/")
  print("Migration complete. Old data at source left in place — remove manually when satisfied.")


def step_write_env(target: Target, cfg: Config) -> None:
  env_path = f"{cfg.deploy_dir}/.env"
  if target.exists(env_path):
    print(f".env already exists — preserving (edit {env_path} to change settings)")
    return
  print("Writing .env...")
  lines = [
    f"DEPLOY_DIR={cfg.deploy_dir}",
    f"REPO_DIR={cfg.repo_dir}",
    f"BACKEND_PORT={cfg.backend_port}",
    f"DATA_DIR={cfg.deploy_dir}/data",
  ]
  if not cfg.no_frontend:
    lines.append(f"FRONTEND_PORT={cfg.frontend_port}")
    lines.append(f"FRONTEND_MODE={cfg.frontend_mode}")
  if cfg.no_frontend:
    lines.append(f"PORT={cfg.backend_port}")
    lines.append("SERVE_MODE=1")
    lines.append(f"SERVICE_USER={cfg.service_user}")
  target.put_text("\n".join(lines) + "\n", env_path)


def step_generate_scripts(target: Target, cfg: Config) -> None:
  if cfg.no_frontend:
    return
  print("Generating start.sh / stop.sh...")
  target.put_text(render_start_sh(cfg), f"{cfg.deploy_dir}/start.sh", mode=0o755)
  target.put_text(render_stop_sh(cfg), f"{cfg.deploy_dir}/stop.sh", mode=0o755)


def step_summary(target: Target, cfg: Config) -> None:
  print()
  print("=" * 42)
  print("Deploy complete!")
  print("=" * 42)
  print()
  print(f"  Deploy dir:  {cfg.deploy_dir}")
  if not cfg.no_frontend:
    print(f"  To start:    {cfg.deploy_dir}/start.sh")
    print(f"  To stop:     {cfg.deploy_dir}/stop.sh")
  print(f"  Config:      {cfg.deploy_dir}/.env")
  print()


# ── Systemd (serve mode) steps ────────────────────────────────────────────────


def step_create_deploy_dir(target: Target, cfg: Config) -> None:
  if target.exists(cfg.deploy_dir):
    return
  print(f"Creating deploy directory {cfg.deploy_dir}...")
  u = cfg.service_user
  target.run(f"sudo install -d -o {u} -g {u} {cfg.deploy_dir}")


def step_secure_env(target: Target, cfg: Config) -> None:
  env_path = f"{cfg.deploy_dir}/.env"
  target.run(f"chmod 0640 {env_path}")


def step_install_units(target: Target, cfg: Config) -> None:
  if cfg.skip_service_install:
    print("Skipping service unit installation (--no-service-install)")
    return
  print("Installing systemd unit files...")
  name = "karaoke-backend.service"
  path = f"/etc/systemd/system/{name}"
  content = render_backend_unit(cfg)
  target.run(
    f"cat | sudo tee {path} > /dev/null",
    stdin=content,
  )
  print(f"  Installed {path}")


def step_systemd_cmd(target: Target, cfg: Config, subcmd: str, skip_when_uninstalled: bool) -> None:
  if skip_when_uninstalled and cfg.skip_service_install:
    print(f"Skipping systemctl {subcmd} (--no-service-install)")
    return
  print(f"Running systemctl {subcmd}...")
  svc = "karaoke-backend.service"
  target.run(f"sudo systemctl {subcmd} {svc}")


def step_systemd_summary(target: Target, cfg: Config) -> None:
  svc = "karaoke-backend.service"
  print()
  print("=" * 42)
  print("Deploy complete!")
  print("=" * 42)
  print()
  print(f"  Deploy dir:  {cfg.deploy_dir}")
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


# ── Deployers ─────────────────────────────────────────────────────────────────


def deploy_full(target: Target, cfg: Config) -> None:
  for step in (
    step_banner,
    step_create_dirs,
    step_ensure_uv,
    step_setup_venv,
    step_install_npm,
    step_migrate_data,
    step_write_env,
    step_generate_scripts,
    step_summary,
  ):
    step(target, cfg)


def deploy_serve(target: Target, cfg: Config) -> None:
  for step in (
    step_banner,
    step_git_pull,
    step_create_deploy_dir,
    step_create_dirs,
    step_ensure_uv,
    step_setup_venv,
    step_write_env,
    step_secure_env,
    step_install_units,
  ):
    step(target, cfg)
  step_systemd_cmd(target, cfg, "daemon-reload", skip_when_uninstalled=True)
  step_systemd_cmd(target, cfg, "enable", skip_when_uninstalled=True)
  step_systemd_cmd(target, cfg, "restart", skip_when_uninstalled=False)
  step_systemd_summary(target, cfg)


def make_target(args: argparse.Namespace) -> Target:
  if args.host:
    return SSHTarget(args.host, user=args.user, key_filename=args.key, port=args.port)
  return LocalTarget()


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
  parser.add_argument(
    "--no-pull",
    action="store_true",
    default=False,
    help="Skip git pull (useful when deploying uncommitted local changes).",
  )
  parser.add_argument(
    "--no-service-install",
    action="store_true",
    default=False,
    help="Skip unit file installation, daemon-reload, and enable (services already installed).",
  )
  parser.add_argument(
    "--recreate-venv",
    action="store_true",
    default=False,
    help="Delete and recreate the venv before installing (fixes distutils uninstall errors).",
  )
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
    repo_dir = os.path.expanduser(os.environ.get("REPO_DIR", "~/karaoke"))
    cfg = Config(
      deploy_dir=deploy_dir,
      repo_dir=repo_dir,
      backend_port=backend_port,
      frontend_port=3002,
      service_user=os.environ.get("SERVICE_USER", os.getenv("USER", "tom")),
      no_frontend=True,
      skip_git_pull=args.no_pull,
      skip_service_install=args.no_service_install,
      recreate_venv=args.recreate_venv,
    )
    deploy_serve(make_target(args), cfg)
  else:
    repo_dir = os.environ.get("REPO_DIR", SCRIPT_DIR if not args.host else "~/karaoke")
    if not args.host:
      repo_dir = os.path.realpath(repo_dir)
    deploy_dir = os.environ.get(
      "DEPLOY_DIR", os.path.expanduser("~/deployments/karaoke")
    )
    cfg = Config(
      deploy_dir=deploy_dir,
      repo_dir=repo_dir,
      backend_port=backend_port,
      frontend_port=int(os.environ.get("FRONTEND_PORT", "3002")),
      frontend_mode=os.environ.get("FRONTEND_MODE", "dev"),
      skip_git_pull=args.no_pull,
      recreate_venv=args.recreate_venv,
      kill_stale_ports=True,
    )
    deploy_full(make_target(args), cfg)


if __name__ == "__main__":
  main()