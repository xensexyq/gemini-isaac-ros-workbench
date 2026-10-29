#!/usr/bin/env python3
"""Prepare pinned external inputs; never install host packages."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, target, expected_sha, expected_bytes=None):
    """Resume network interruptions and atomically publish verified bytes."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and sha256(target) == expected_sha:
        if expected_bytes is None or target.stat().st_size == expected_bytes:
            return target
    partial = target.with_name(target.name + '.part')
    for attempt in range(4):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if expected_bytes is not None and offset > expected_bytes:
                raise ValueError('Partial download exceeds pinned length')
            if expected_bytes is None or offset != expected_bytes:
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=90) as response:
                    mode = 'wb'
                    if offset and response.status == 206:
                        actual = response.headers.get('Content-Range', '')
                        if not actual.startswith(f'bytes {offset}-'):
                            raise ValueError('Invalid resumed HTTP range')
                        mode = 'ab'
                    elif response.status != 200:
                        raise ValueError(f'Unexpected HTTP status {response.status}')
                    with partial.open(mode) as stream:
                        shutil.copyfileobj(response, stream, length=1024 * 1024)
            if expected_bytes is not None and partial.stat().st_size != expected_bytes:
                raise ValueError('Pinned byte count does not match')
            if sha256(partial) != expected_sha:
                partial.unlink()
                raise ValueError('Pinned SHA-256 does not match')
            partial.replace(target)
            return target
        except (OSError, ValueError):
            if attempt == 3:
                raise
            time.sleep(1 + attempt)


def safe_relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value:
        raise ValueError(f'Unsafe dependency path: {value}')
    return Path(*path.parts)


def source_bytes(path):
    return os.readlink(path).encode() if path.is_symlink() else path.read_bytes()


def verify_source(source, manifest):
    expected = {item['path'] for item in manifest['files']}
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*')
              if p.is_file() or p.is_symlink()}
    if expected != actual:
        raise ValueError('Driver source file set differs from the pinned manifest')
    for item in manifest['files']:
        path = source / safe_relative(item['path'])
        if hashlib.sha256(source_bytes(path)).hexdigest() != item['sha256']:
            raise ValueError(f'Existing driver source was modified: {item["path"]}')


def prepare_driver(root, lock):
    manifest = json.loads((root / 'docker/orbbec-source-manifest.json').read_text())
    if manifest['revision'] != lock['orbbec_revision']:
        raise ValueError('Driver revision differs from dependencies.lock.json')
    source = root / 'docker/orbbec-src'
    def fetch(item):
        relative = safe_relative(item['path'])
        path = source / relative
        if path.exists() or path.is_symlink():
            if hashlib.sha256(source_bytes(path)).hexdigest() != item['sha256']:
                raise ValueError(f'Preserving modified source; restore it explicitly: {relative}')
            return
        url = ('https://raw.githubusercontent.com/orbbec/OrbbecSDK_ROS2/' +
               manifest['revision'] + '/' + urllib.parse.quote(item['path']))
        cached = root / '.cache/orbbec-blobs' / item['sha256']
        download(url, cached, item['sha256'], item['bytes'])
        path.parent.mkdir(parents=True, exist_ok=True)
        # Git symlinks are small blobs; preserve their identity without following them.
        if item['git_blob'] and item['path'].endswith(('.so', '.so.2')):
            data = cached.read_bytes()
            if len(data) < 256 and b'\x00' not in data:
                target = data.decode()
                resolved = (path.parent / target).resolve()
                if source.resolve() not in resolved.parents:
                    raise ValueError('SDK symlink leaves source tree')
                path.symlink_to(target)
                return
        shutil.copyfile(cached, path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(fetch, manifest['files']))
    verify_source(source, manifest)
    print(f'Orbbec source verified: {len(manifest["files"])} files')


def file_inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(source_bytes(p)).hexdigest()
            for p in root.rglob('*') if p.is_file() or p.is_symlink()}


def prepare_examples(root, lock):
    spec = lock['examples_package']
    archive = download(spec['url'], root / '.cache/nvblox-examples.deb',
                       spec['sha256'], spec['bytes'])
    target = root / 'docker/official-examples'
    with tempfile.TemporaryDirectory(prefix='nvblox-examples-', dir=root / '.cache') as temp:
        subprocess.run(['dpkg-deb', '-x', str(archive), temp], check=True)
        expected = file_inventory(Path(temp))
        if target.exists():
            if file_inventory(target) != expected:
                raise ValueError('Preserving modified example files; restore them explicitly')
        else:
            shutil.copytree(temp, target, symlinks=True)
    print('Pinned nvblox example configuration prepared (not registered as an APT install)')


def extract_dataset(archive, output):
    with tarfile.open(archive) as stream:
        members = stream.getmembers()
        required = sum(item.size for item in members)
        if required + 2 * 1024**3 > shutil.disk_usage(output).free:
            raise RuntimeError('Insufficient free space for dataset extraction plus 2 GiB reserve')
        stream.extractall(output, members=members, filter='data')


def prepare_dataset(root, lock, name):
    spec = lock['datasets'][name]
    assets = root / 'assets'
    assets.mkdir(exist_ok=True)
    marker = root / '.cache' / f'{name}-extracted.json'
    metadata = assets / spec['metadata']
    if marker.exists() and metadata.exists():
        previous = json.loads(marker.read_text())
        if previous.get('archive_sha256') == spec['sha256'] and \
           previous.get('metadata_sha256') == sha256(metadata):
            print(f'{name}: extracted inputs already prepared')
            return
    url = (f'https://api.ngc.nvidia.com/v2/resources/nvidia/isaac/'
           f'isaac_ros_{name}_assets/versions/{spec["version"]}/files/quickstart.tar.gz')
    archive = download(url, root / '.cache' / f'{name}-quickstart.tar.gz',
                       spec['sha256'], spec['bytes'])
    extract_dataset(archive, assets)
    if not metadata.is_file():
        raise ValueError('Official dataset is missing expected metadata')
    marker.write_text(json.dumps({'archive_sha256': spec['sha256'],
                                 'metadata_sha256': sha256(metadata)}, indent=2))
    print(f'{name}: checksum verified and extracted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['examples', 'driver', 'visual_slam', 'nvblox', 'all'])
    args = parser.parse_args()
    (ROOT / '.cache').mkdir(exist_ok=True)
    lock = json.loads((ROOT / 'config/dependencies.lock.json').read_text())
    if args.target in ('examples', 'all'):
        prepare_examples(ROOT, lock)
    if args.target in ('driver', 'all'):
        prepare_driver(ROOT, lock)
    for name in ('visual_slam', 'nvblox'):
        if args.target in (name, 'all'):
            prepare_dataset(ROOT, lock, name)


if __name__ == '__main__':
    main()
