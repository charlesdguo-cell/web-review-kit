"""A nonblocking, canonical-directory writer lock held for the service lifetime."""
from contextlib import contextmanager
import fcntl
from pathlib import Path


class DataLockError(ValueError):
    code = 'data_writer_conflict'
    exit_code = 3


@contextmanager
def acquire_data_lock(data_dir: Path):
    data = Path(data_dir).resolve()
    data.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink a lock file: a waiting process could otherwise lock an old inode.
    path = data.parent / ('.' + data.name + '.web-review.lock')
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DataLockError('Another review writer owns data directory: ' + str(data)) from error
        try:
            yield data
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
