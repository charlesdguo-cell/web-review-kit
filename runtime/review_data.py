"""HTTP review data operations that preserve frozen evidence and project identity."""
import copy
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class ReviewDataError(ValueError):
    def __init__(self, message, code='review_unavailable', exit_code=2):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReviewClient:
    def __init__(self, base_url: str, project_id: str):
        parts = urlsplit(base_url)
        if (parts.scheme not in ('http', 'https') or not parts.netloc or parts.query or
                parts.fragment or parts.username or parts.password):
            raise ReviewDataError('Expected a service HTTP(S) base URL')
        self.base_url = base_url.rstrip('/') + '/'
        self.project_id = project_id
        self.origin = parts.scheme + '://' + parts.netloc
        self._opener = build_opener(_NoRedirect)

    def _request(self, method, path, payload=None):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        headers = {'Origin': self.origin, 'Content-Type': 'application/json'}
        request = Request(urljoin(self.base_url, path), body, headers, method=method)
        try:
            with self._opener.open(request, timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get('error', str(error))
            except (ValueError, AttributeError):
                detail = str(error)
            raise ReviewDataError(str(detail), 'review_conflict' if error.code == 409 else 'review_http_error',
                                  3 if error.code == 409 else 2) from error
        except (OSError, ValueError) as error:
            raise ReviewDataError('Review request failed: ' + str(error)) from error

    def _identity(self):
        health = self._request('GET', '__review/health')
        if not isinstance(health, dict) or health.get('projectId') != self.project_id:
            raise ReviewDataError('Review service projectId does not match configured project', 'project_conflict', 3)

    def list(self) -> list[dict]:
        self._identity()
        response = self._request('GET', '__review/comments')
        comments = response.get('comments') if isinstance(response, dict) else None
        if not isinstance(comments, list) or any(not isinstance(item, dict) for item in comments):
            raise ReviewDataError('Invalid review comments response')
        return comments

    def show(self, identity: str) -> dict:
        matches = [item for item in self.list() if item.get('id') == identity or str(item.get('number')) == str(identity)]
        if len(matches) != 1:
            raise ReviewDataError('Review identity missing or ambiguous: ' + str(identity))
        return matches[0]

    def mark_changed(self, snapshot: dict, resolution: str) -> dict:
        if not isinstance(snapshot, dict) or not snapshot.get('id') or not snapshot.get('updatedAt'):
            raise ReviewDataError('A frozen comment snapshot with id and updatedAt is required')
        if not isinstance(resolution, str) or not resolution.strip():
            raise ReviewDataError('A nonempty implementation resolution is required')
        desired = {**copy.deepcopy(snapshot), 'status': 'changed', 'resolution': resolution}
        def content(record):
            return {key: value for key, value in record.items() if key != 'updatedAt'}
        current = self.show(snapshot['id'])
        if current != snapshot:
            # A successful POST may lose its response. Identical state is satisfied,
            # but any unrelated field change remains a conflict; never refresh timestamps.
            if content(current) == content(desired):
                return current
            raise ReviewDataError('Frozen review snapshot is stale', 'review_conflict', 3)
        self._identity()
        try:
            response = self._request('POST', '__review/comments',
                                     {'comment': desired, 'expectedUpdate': snapshot['updatedAt'], 'projectId': self.project_id})
        except OSError as error:
            raise ReviewDataError('Review response unavailable; retry the identical frozen submission: ' + str(error)) from error
        saved = response.get('comment')
        verified = self.show(snapshot['id'])
        if (not isinstance(saved, dict) or verified != saved or content(saved) != content(desired)):
            raise ReviewDataError('Review readback differs from submitted evidence', 'review_conflict', 3)
        return verified

    def export(self, destination: Path) -> dict:
        comments = self.list()
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        # Raw URLs and all extensions remain intact; local copies have a separate map.
        (destination / 'comments.json').write_text(json.dumps(comments, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        prefix = urlsplit(self.base_url).path.rstrip('/') + '/__review/'
        evidence = []
        seen = set()
        for comment in comments:
            urls = [comment.get('screenshot')] + [image.get('url') for image in comment.get('attachments', []) if isinstance(image, dict)]
            for value in urls:
                if not isinstance(value, str):
                    continue
                url = urljoin(self.origin + '/', value)
                parts = urlsplit(url)
                decoded = unquote(parts.path)
                if (parts.scheme + '://' + parts.netloc != self.origin or parts.query or parts.fragment or
                        not any(decoded.startswith(prefix + kind + '/') for kind in ('screenshots', 'attachments'))):
                    continue
                relative = Path(decoded[len(prefix):])
                if '..' in relative.parts or value in seen:
                    continue
                self._identity()
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with self._opener.open(Request(url), timeout=10) as response:
                        target.write_bytes(response.read())
                except OSError as error:
                    raise ReviewDataError('Evidence export failed: ' + str(error)) from error
                seen.add(value)
                evidence.append({'url': value, 'path': relative.as_posix()})
        (destination / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {'directory': str(destination.resolve()), 'comments': len(comments), 'evidence': evidence}
