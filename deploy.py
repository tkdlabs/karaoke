#!/usr/bin/env python3
"""Deployment script for Karaoke.

Usage:
  python deploy.py                              # deploys to ~/deployments/karaoke
  DEPLOY_DIR=/srv/karaoke python deploy.py      # custom deploy dir
  DEPLOY_DIR=... FRONTEND_MODE=prod python deploy.py

Environment variables:
  DEPLOY_DIR      Deploy directory (default: ~/deployments/karaoke)
  AI_DEV_PATH     ai-dev repo root (default: inferred from script location)
  BACKEND_PORT    Backend port (default: 8001)
  FRONTEND_PORT   Frontend port (default: 3002)
  FRONTEND_MODE   "dev" or "prod" (default: dev)
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_DEV_PATH = os.environ.get(
  "AI_DEV_PATH", os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
)

sys.path.insert(0, os.path.join(AI_DEV_PATH, "workflows/deployment/src"))

from deploy_lib import DeployConfig, Deployer, LocalTarget  # noqa: E402

config = DeployConfig(
  app_name="Karaoke",
  project_subpath="frontends/karaoke",
  deploy_dir=os.environ.get("DEPLOY_DIR", os.path.expanduser("~/deployments/karaoke")),
  ai_dev_path=AI_DEV_PATH,
  backend_port=int(os.environ.get("BACKEND_PORT", "8001")),
  frontend_port=int(os.environ.get("FRONTEND_PORT", "3002")),
  frontend_mode=os.environ.get("FRONTEND_MODE", "dev"),
  migrate_data_from="data",
  kill_stale_ports=True,
)

Deployer(config, LocalTarget()).deploy()
