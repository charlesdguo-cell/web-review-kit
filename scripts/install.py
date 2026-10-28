#!/usr/bin/env python3
"""Install a verified release and select it as the global default unless opted out."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from release_manager import install_release, installed_root, verify_release, activate_global_release, ReleaseError, _version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--archive', type=Path)
    source.add_argument('--github-version', help='Exact version in charlesdguo-cell/web-review-kit; uses existing gh login')
    parser.add_argument('--skill-link', type=Path, help='Explicit discovery symlink destination; never writes global config by default')
    activation = parser.add_mutually_exclusive_group()
    activation.add_argument('--activate-global', dest='activate_global', action='store_true',
                            help='Atomically select this verified release as INSTALL/current (default)')
    activation.add_argument('--no-activate-global', dest='activate_global', action='store_false',
                            help='Install without changing INSTALL/current; an explicit Skill link stays version-pinned')
    parser.set_defaults(activate_global=True)
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix='web-review-download-') as temporary:
            archive = args.archive
            if args.github_version:
                version = _version(args.github_version)
                name = 'web-review-kit-' + version + '.tar.gz'
                result = subprocess.run(['gh', 'release', 'download', 'v' + version,
                                         '--repo', 'charlesdguo-cell/web-review-kit',
                                         '--pattern', name + '*', '--dir', temporary], capture_output=True, text=True)
                if result.returncode:
                    raise ReleaseError('Private release unavailable; verify existing gh login and repository access. No credentials are bundled.', 'private_release_unavailable', 2)
                archive = Path(temporary) / name
                checksum = (Path(temporary) / (name + '.sha256')).read_text().split()
                if checksum != [hashlib.sha256(archive.read_bytes()).hexdigest(), name]:
                    raise ReleaseError('Downloaded archive checksum mismatch')
            release = install_release(archive, args.install_root)
        activation = {}
        if args.activate_global:
            activation = activate_global_release(release, args.install_root, skill_link=args.skill_link)
        elif args.skill_link:
            link = args.skill_link.expanduser().absolute()
            target = release / 'skills/web-review'
            if link.exists() or link.is_symlink():
                if not link.is_symlink() or link.resolve() != target:
                    raise ReleaseError('Discovery destination already exists; preserved: ' + str(link))
            else:
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target, target_is_directory=True)
        print(json.dumps({'ok': True, 'toolVersion': verify_release(release)['version'],
                          'installRoot': str(installed_root(release)), 'releaseRoot': str(release),
                          'skill': str(release / 'skills/web-review/SKILL.md'), 'serviceStarted': False, **activation}))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': getattr(error, 'code', 'installation_unavailable'), 'message': str(error)}))
        return getattr(error, 'exit_code', 2)


if __name__ == '__main__':
    sys.exit(main())
