#!/usr/bin/env python3
"""Build a deterministic Web Review Kit bundle from the explicit source root."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from release_manager import package_release

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        archive = package_release(args.source_root, args.destination)
        print(json.dumps({'ok': True, 'archive': str(archive), 'manifest': str(archive.parent / 'release-manifest.json')}))
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': getattr(error, 'code', 'package_unavailable'), 'message': str(error)}))
        sys.exit(getattr(error, 'exit_code', 2))
