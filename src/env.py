"""Secrets from the environment or the project's .env file (.env is in .gitignore)."""

import os
from pathlib import Path


def env_value(name, project_root):
    """`name` from the environment, else from project_root/.env, else None."""
    if os.environ.get(name):
        return os.environ[name].strip()
    env_file = Path(project_root) / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name and value.strip():
                return value.strip().strip('"').strip("'")
    return None
