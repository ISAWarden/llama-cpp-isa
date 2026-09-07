"""Exercise upstream archive merging and ISA release links with small real archives."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
TAG = 'isa-42-123abcd'


class PackagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = ROOT / 'llama.cpp/.github/workflows/release.yml'
        target = self.root / 'llama.cpp/.github/workflows/release.yml'
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)
        steps = yaml.safe_load(source.read_text())['jobs']['release']['steps']
        body = next(s for s in steps if s.get('id') == 'create_release')['with']['body']
        body = body.replace('${{ steps.tag.outputs.name }}', TAG)
        body = re.sub(r'\$\{\{ needs\.[^}]+\}\}', '2026.3.1', body)
        self.artifacts = self.root / 'artifact'
        self.artifacts.mkdir()
        for name in set(re.findall(r'/releases/download/[^/]+/([^\s)]+)', body)):
            if 's390x' in name or name.endswith('-ui.tar.gz'):
                continue
            if '-bin-win-' in name and name.startswith('llama-' + TAG):
                name = name.replace('llama-' + TAG, 'llama', 1)
            path = self.artifacts / name
            if name.endswith('.zip'):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('llama-server.exe' if '-cpu-' in name else 'backend.dll', name)
            else:
                with tarfile.open(path, 'w:gz'):
                    pass
        (self.root / 'ui-dist').mkdir()
        (self.root / 'ui-dist/index.html').write_text('UI fixture')
        (self.root / 'release-manifest.json').write_text(json.dumps({
            'project_commit': '123abcd' + '0' * 33,
            'upstream_commit': '1' * 40, 'features': ['turboquant'],
        }))

    def package(self):
        return subprocess.run(['python3', str(ROOT / '.github/scripts/package-release.py')],
                              cwd=self.root, env=dict(os.environ, RELEASE_TAG=TAG,
                                  GITHUB_SERVER_URL='https://github.com', GITHUB_REPOSITORY='test/isa'),
                              capture_output=True, text=True)

    def test_merge_links_checksums(self):
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        release = self.root / 'release'
        with zipfile.ZipFile(release / f'llama-{TAG}-bin-win-vulkan-x64.zip') as archive:
            self.assertIn('llama-server.exe', archive.namelist())
            self.assertIn('backend.dll', archive.namelist())
        notes = (self.root / 'release-notes.md').read_text()
        self.assertNotIn('ggml-org/llama.cpp/releases', notes)
        self.assertNotIn('s390x', notes)
        for name in re.findall(r'/releases/download/[^/]+/([^\s)]+)', notes):
            self.assertTrue((release / name).is_file(), name)
        for line in (release / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(digest, hashlib.sha256((release / name).read_bytes()).hexdigest())

    def test_missing_platform_asset_fails(self):
        (self.artifacts / f'llama-{TAG}-bin-ubuntu-vulkan-arm64.tar.gz').unlink()
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Release link has no asset', result.stderr)


if __name__ == '__main__':
    unittest.main()
