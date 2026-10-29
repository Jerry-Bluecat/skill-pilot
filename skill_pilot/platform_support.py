"""Small OS boundary for user identity and process locks."""
import os
import time
from pathlib import Path


def readlink(path):
    value = os.readlink(path)
    if os.name == 'nt':
        if value.startswith('\\\\?\\UNC\\'):
            return '\\\\' + value[8:]
        return value.removeprefix('\\\\?\\')
    return value


def rmtree(path, ignore_errors=False):
    import shutil
    import stat
    if os.name != 'nt':
        return shutil.rmtree(path, ignore_errors=ignore_errors)
    def retry(function, name, error):
        try:
            if os.name != 'nt' or not isinstance(error, PermissionError):
                raise error
            os.chmod(name, stat.S_IWRITE)
            function(name)
        except OSError:
            if not ignore_errors:
                raise
    return shutil.rmtree(path, onexc=retry)


def is_junction(path):
    return os.name == 'nt' and Path(path).is_junction()


def create_links(links):
    """Create staged links after files, resolving chains before Windows types them."""
    pending = list(links)
    while pending:
        remaining = []
        for path, target in pending:
            destination = path.parent / target
            if destination.exists():
                path.symlink_to(str(Path(target)) if os.name == 'nt' else target,
                                target_is_directory=destination.is_dir())
            else:
                remaining.append((path, target))
        if len(remaining) == len(pending):
            # Dangling links retain their text; the existing source-boundary
            # validation still decides whether they may be installed.
            for path, target in remaining:
                path.symlink_to(str(Path(target)) if os.name == 'nt' else target)
            break
        pending = remaining


def copytree(source, destination, **options):
    """Preserve Windows directory-link types instead of copying them as files."""
    import shutil
    import stat
    if os.name != 'nt' or not options.get('symlinks'):
        return shutil.copytree(source, destination, **options)
    source, destination = Path(source), Path(destination)
    ignore = options.pop('ignore', None)
    links = []
    def skip_links(directory, names):
        skipped = set(ignore(directory, names) if ignore else [])
        for name in names:
            path = Path(directory) / name
            if name not in skipped and path.is_symlink():
                links.append((path, destination / path.relative_to(source), readlink(path),
                              bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY)))
                skipped.add(name)
        return skipped
    result = shutil.copytree(source, destination, ignore=skip_links, **options)
    for original, path, target, directory in links:
        path.symlink_to(str(Path(target)), target_is_directory=directory)
        shutil.copystat(original, path, follow_symlinks=False)
    return result


def user_home():
    if os.name == 'nt':
        return Path(os.environ['USERPROFILE']).resolve()
    import pwd
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()


def user_id():
    return os.environ.get('USERNAME', 'user') if os.name == 'nt' else os.getuid()


if os.name != 'nt':
    import fcntl
else:
    import msvcrt

    class WindowsLocks:
        LOCK_EX = 2
        LOCK_NB = 4

        @staticmethod
        def flock(file, operation):
            # Lock beyond the payload: another launcher must still read the URL.
            # Windows releases the byte-range lock when the descriptor closes.
            position = file.tell()
            try:
                file.seek(0x7fffffff)
                while True:
                    try:
                        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                        return
                    except OSError as error:
                        if error.errno not in (13, 36):
                            raise
                        if operation & WindowsLocks.LOCK_NB:
                            raise BlockingIOError('Another process holds the lock') from error
                        time.sleep(0.05)
            finally:
                file.seek(position)

    fcntl = WindowsLocks()


def check_directory_links():
    """Fail before a migration touches skills when Windows denies links."""
    if os.name != 'nt':
        return
    import tempfile
    with tempfile.TemporaryDirectory(prefix='skill-pilot-link-check-') as directory:
        root = Path(directory)
        (root / 'target').mkdir()
        try:
            (root / 'link').symlink_to(root / 'target', target_is_directory=True)
        except OSError as error:
            raise ValueError('请先在 Windows 设置中开启开发者模式，再重试；技能文件没有改动。') from error
