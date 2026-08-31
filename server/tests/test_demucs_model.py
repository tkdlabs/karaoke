"""Tests for DEMUCS_MODEL env selection in the real demucs.py module.

demucs.py only imports the stdlib, so it can be loaded directly without the
conftest stub (which exists to avoid real external imports in main.py).
"""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

_DEMUCS_PATH = Path(__file__).parent.parent / "demucs.py"


def _load_demucs(env_model: str | None):
  old = os.environ.get("DEMUCS_MODEL")
  if env_model:
    os.environ["DEMUCS_MODEL"] = env_model
  else:
    os.environ.pop("DEMUCS_MODEL", None)
  try:
    spec = importlib.util.spec_from_file_location("demucs_model_test", _DEMUCS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
  finally:
    if old is None:
      os.environ.pop("DEMUCS_MODEL", None)
    else:
      os.environ["DEMUCS_MODEL"] = old


def test_default_model_is_htdemucs() -> None:
  module = _load_demucs(None)
  assert module.DEFAULT_MODEL == "htdemucs"
  assert module.run_demucs.__defaults__[0] == "htdemucs"


def test_env_var_selects_model() -> None:
  module = _load_demucs("htdemucs_ft")
  assert module.DEFAULT_MODEL == "htdemucs_ft"
  assert module.run_demucs.__defaults__[0] == "htdemucs_ft"


def test_run_demucs_passes_model_flag() -> None:
  module = _load_demucs("htdemucs_ft")
  with patch.object(module.subprocess, "run") as mock_run:
    mock_run.return_value.returncode = 0
    out = module.run_demucs(Path("/in.mp3"), Path("/tmp"))
  args = mock_run.call_args[0][0]
  assert "-n" in args
  assert args[args.index("-n") + 1] == "htdemucs_ft"
  assert out == Path("/tmp") / "htdemucs_ft" / "in"