#!/usr/bin/env python3
"""Exercise a frozen review server, including concurrent large-video metadata reads.

Run with --service /path/to/server.py. For memory regression, run inside a
256 MiB container; a successful small Range must not allocate its entire file.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import json
from pathlib import Path
import resource
import sys
import subprocess
import unittest
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run_checks(service):
    sys.path.insert(0, str(service.resolve().parent))
    spec = importlib.util.spec_from_file_location('review_stream_test_server', service)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = 0
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / 'site'
        root.mkdir()
        sample = bytes(range(256)) * 4
        (root / 'sample.mp4').write_bytes(sample)
        (root / 'empty.mp4').touch()
        large_size = 64 * 1024 * 1024
        with (root / 'large.mp4').open('wb') as stream:
            stream.truncate(large_size)
        server = module.make_server(root, Path(folder) / 'data', 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:' + str(server.server_port)

        def request(path, headers=None, method='GET'):
            try:
                response = urlopen(Request(base + path, headers=headers or {}, method=method), timeout=20)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read()

        try:
            for requested, start, end in [
                ('bytes=0-', 0, 1023), ('bytes=100-199', 100, 199),
                ('bytes=1000-9999', 1000, 1023), ('bytes=-20', 1004, 1023),
                ('bytes=-9999', 0, 1023),
            ]:
                status, headers, body = request('/sample.mp4', {'Range': requested})
                assert status == 206 and body == sample[start:end + 1], requested
                assert headers['Content-Range'] == f'bytes {start}-{end}/1024'
                assert int(headers['Content-Length']) == len(body)
                checks += 1
            for path, requested, size in [
                ('/sample.mp4', 'bytes=1024-', 1024),
                ('/sample.mp4', 'bytes=8-2', 1024),
                ('/sample.mp4', 'bytes=-0', 1024),
                ('/empty.mp4', 'bytes=0-', 0),
            ]:
                status, headers, body = request(path, {'Range': requested})
                assert status == 416 and headers['Content-Range'] == f'bytes */{size}' and body == b''
                checks += 1
            for headers in [{}, {'Range': 'bytes=bad'}, {'Range': 'bytes=0-1,4-5'},
                            {'Range': 'bytes=2-', 'If-Range': '"unknown-version"'}]:
                status, _, body = request('/sample.mp4', headers)
                assert status == 200 and body == sample
                checks += 1
            status, headers, body = request('/large.mp4', {'Range': 'bytes=2-'}, method='HEAD')
            assert status == 200 and int(headers['Content-Length']) == large_size and body == b''
            checks += 1
            barrier = threading.Barrier(16)

            def metadata(_):
                barrier.wait(timeout=10)
                status, headers, body = request('/large.mp4', {'Range': 'bytes=0-31'})
                assert status == 206 and body == bytes(32)
                assert headers['Content-Range'] == f'bytes 0-31/{large_size}'
                return True

            with ThreadPoolExecutor(max_workers=16) as pool:
                checks += sum(pool.map(metadata, range(16)))
            opened = threading.Barrier(16)

            def cancelled_metadata(_):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=20)
                response = None
                try:
                    client.request('GET', '/large.mp4', headers={'Range': 'bytes=0-'})
                    response = client.getresponse()
                    assert response.status == 206
                    assert response.read(4096) == bytes(4096)
                    # Keep downloads open together, as with visible video cards.
                    opened.wait(timeout=20)
                    return True
                finally:
                    if response is not None:
                        response.close()
                    client.close()

            with ThreadPoolExecutor(max_workers=16) as pool:
                checks += sum(pool.map(cancelled_metadata, range(16)))
            # Browsers cancel full/suffix downloads once they have enough metadata.
            # Subsequent requests must remain healthy after that disconnect.
            for requested in [None, 'bytes=-67108864']:
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                client.request('GET', '/large.mp4', headers={'Range': requested} if requested else {})
                response = client.getresponse()
                assert response.status == (206 if requested else 200)
                assert response.read(4096) == bytes(4096)
                response.close()
                client.close()
                assert request('/sample.mp4')[2] == sample
                checks += 1
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mib = rss / (1024 * 1024 if sys.platform == 'darwin' else 1024)
    assert peak_mib < 128, f'Peak RSS exceeded bound: {peak_mib:.1f} MiB'
    print(json.dumps({'passed': checks, 'failed': 0, 'concurrentRequests': 16,
                      'fixtureMiB': 64, 'peakRSSMiB': round(peak_mib, 2)}), flush=True)


class MediaStreamingTests(unittest.TestCase):
    def test_concurrent_large_media_with_bounded_memory(self):
        service = Path(__file__).resolve().parents[1] / 'runtime/server.py'
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                 '--service', str(service)], text=True,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['passed'], 48)


if __name__ == '__main__':
    if '--service' in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--service', type=Path, required=True)
        run_checks(parser.parse_args().service)
    else:
        unittest.main(verbosity=2)
