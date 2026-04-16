import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def load_config(path: str | Path = "agent_config.yaml") -> dict:
    path = Path(path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_api_key(provider_cfg: dict) -> str | None:
    env_var = provider_cfg.get("api_key_env")
    if env_var:
        return os.environ.get(env_var)
    raw = provider_cfg.get("api_key", "")
    if raw.startswith("${") and raw.endswith("}"):
        return os.environ.get(raw[2:-1])
    return raw or None
