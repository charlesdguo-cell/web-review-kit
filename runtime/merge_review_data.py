"""Import missing review IDs while the service is stopped; never overwrite server reviews."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil


def merge(source, target):
    source, target = Path(source), Path(target)
    incoming = json.loads((source / 'comments.json').read_text())
    manifest = target / 'comments.json'
    existing = json.loads(manifest.read_text()) if manifest.exists() else []
    known = {c['id']: c for c in existing}
    assert len(known) == len(existing), 'Server has duplicate IDs'
    assert len({c['id'] for c in incoming}) == len(incoming), 'Import has duplicate IDs'
    numbers = {c['number'] for c in existing}
    result = {'imported': [], 'alreadyPresent': [], 'keptServerVersion': [], 'screenshots': {}, 'attachments': {}}
    planned = []
    for comment in incoming:
        identity = comment['id']
        assert re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', identity), 'Invalid ID'
        if identity in known:
            result['alreadyPresent' if comment == known[identity] else 'keptServerVersion'].append(identity)
            continue
        screenshot = source / 'screenshots' / (identity + '.png')
        image = screenshot.read_bytes()
        assert image.startswith(b'\x89PNG\r\n\x1a\n'), 'Missing or invalid PNG'
        destination = target / 'screenshots' / screenshot.name
        assert not destination.exists() or destination.read_bytes() == image, 'Existing screenshot differs'
        planned.append((screenshot, destination))
        result['screenshots'][identity] = hashlib.sha256(image).hexdigest()
        for attachment in comment.get('attachments', []):
            match = re.fullmatch(r'/__review/attachments/([a-zA-Z0-9_-]{8,80})/([a-f0-9]{64}\.(?:png|jpg|webp|gif))', attachment['url'])
            assert match and match[1] == identity, 'Invalid attachment path'
            relative = Path('attachments') / identity / match[2]
            attachment_source = source / relative
            content = attachment_source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            assert digest == match[2].split('.')[0], 'Attachment content differs from its filename'
            attachment_target = target / relative
            assert not attachment_target.exists() or attachment_target.read_bytes() == content, 'Existing attachment differs'
            planned.append((attachment_source, attachment_target))
            result['attachments'][attachment['url']] = digest
        if comment['number'] in numbers:
            comment['originalNumber'] = comment['number']
            comment['number'] = max(numbers, default=0) + 1
        numbers.add(comment['number'])
        existing.append(comment)
        result['imported'].append(identity)
    target.mkdir(parents=True, exist_ok=True)
    for screenshot, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(screenshot), str(destination))
    temporary = target / 'comments.import.tmp'
    temporary.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n')
    os.replace(str(temporary), str(manifest))
    result['total'] = len(existing)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(merge(args.source, args.target), ensure_ascii=False, indent=2))
