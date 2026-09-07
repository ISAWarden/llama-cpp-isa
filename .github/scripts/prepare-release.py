#!/usr/bin/env python3
"""Archive the pinned, fully patched source in a fresh CI checkout (POSIX only)."""
import hashlib
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    spec = importlib.util.spec_from_file_location('patch_manager', ROOT / 'configure.py')
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    if manager.git('status', '--porcelain').strip():
        raise RuntimeError('Release preparation requires a pristine submodule checkout')
    subprocess.run(['python3', str(ROOT / 'configure.py'), '--all'], check=True)
    state = json.loads((ROOT / '.patch-state/selection.json').read_text())
    source_tree = manager.tree(state['base'], state['patches'])
    sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    metadata = {
        'project_commit': sha,
        'upstream_commit': state['base'],
        'source_tree': source_tree,
        'features': state['enabled'],
        'patch_sha256': {name: hashlib.sha256((ROOT / 'patches' / (name + '.patch')).read_bytes()).hexdigest()
                         for name in state['enabled']},
    }
    (ROOT / 'release-manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'source.tar'
        subprocess.run(['git', '-C', str(ROOT / 'llama.cpp'), 'archive', '--format=tar',
                        '-o', str(archive), source_tree], check=True)
        with tarfile.open(archive, 'a') as tar:
            tar.add(ROOT / 'release-manifest.json', arcname='isa-release/release-manifest.json')
            tar.add(ROOT / 'patches', arcname='isa-release/patches')
            tar.add(ROOT / 'README.md', arcname='isa-release/README.md')
        with archive.open('rb') as source, gzip.open(ROOT / 'patched-source.tar.gz', 'wb') as target:
            shutil.copyfileobj(source, target)
    # Verify reversibility before allowing any platform jobs to start.
    subprocess.run(['python3', str(ROOT / 'configure.py'), '--none'], check=True)
    if manager.git('status', '--porcelain').strip():
        raise RuntimeError('Patch round trip left the submodule dirty')
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'tag=isa-{os.environ["GITHUB_RUN_NUMBER"]}-{sha[:7]}\n')


if __name__ == '__main__':
    main()
