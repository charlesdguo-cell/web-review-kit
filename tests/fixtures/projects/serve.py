"""Synthetic configured HTTP service; never enables a real task bridge."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'runtime'))
from project_config import load_project_config
from server import make_server

config = load_project_config(Path(sys.argv[1]))
assert not config.codex['enabled']
with make_server(config.web_root, config.data_dir, config.server['port'],
                 config.server['basePath'], config.server['publicOrigins'],
                 config.server['host'], project_config=config) as server:
    server.serve_forever()
