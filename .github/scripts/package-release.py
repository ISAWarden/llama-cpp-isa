#!/usr/bin/env python3
"""Use upstream's archive merge and release layout, linking only real ISA assets."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import yaml


def main():
    tag = os.environ['RELEASE_TAG']
    if not re.fullmatch(r'isa-[0-9]+-[0-9a-f]{7}', tag):
        raise ValueError('Invalid release identifier')
    upstream = yaml.safe_load(Path('llama.cpp/.github/workflows/release.yml').read_text())
    steps = {s.get('id'): s for s in upstream['jobs']['release']['steps']}
    for name in ('move_artifacts', 'package_ui'):
        script = steps[name]['run'].replace('${{ steps.tag.outputs.name }}', tag)
        if '${{' in script:
            raise ValueError('Unresolved expression in upstream packaging script')
        subprocess.run(['bash', '-euo', 'pipefail', '-c', script], check=True)
    release = Path('release')
    manifest = Path('release-manifest.json')
    data = json.loads(manifest.read_text())
    (release / manifest.name).write_bytes(manifest.read_bytes())
    with (release / 'SHA256SUMS').open('w') as sums:
        for asset in sorted(release.iterdir()):
            if asset.name != 'SHA256SUMS':
                with asset.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                sums.write(f'{digest}  {asset.name}\n')
    base_url = f'{os.environ["GITHUB_SERVER_URL"]}/{os.environ["GITHUB_REPOSITORY"]}'
    body = steps['create_release']['with']['body']
    # Keep upstream platform labels/order; omit unavailable runners and disabled builds.
    body = body[body.index('**macOS/iOS:**'):]
    body = re.sub(r'\*\*openEuler:\*\*.*?(?=\*\*UI:)', '', body, flags=re.S)
    body = body.replace('https://github.com/ggml-org/llama.cpp', base_url)
    body = body.replace('${{ steps.tag.outputs.name }}', tag)
    for job, platform in [('ubuntu-24-openvino', 'ubuntu'), ('windows-openvino', 'win')]:
        matches = list(release.glob(f'llama-{tag}-bin-{platform}-openvino-*-x64.*'))
        if len(matches) != 1:
            raise ValueError(f'Expected one {platform} OpenVINO archive')
        version = matches[0].name.split('-openvino-', 1)[1].split('-x64', 1)[0]
        body = body.replace('${{ needs.' + job + '.outputs.openvino_version }}', version)
    lines = []
    for line in body.splitlines():
        if 'DISABLED' in line or 's390x' in line:
            continue
        for filename in re.findall(r'/releases/download/[^/]+/([^\s)]+)', line):
            if not (release / filename).is_file():
                raise ValueError(f'Release link has no asset: {filename}')
        lines.append(line)
    if '${{' in '\n'.join(lines):
        raise ValueError('Unresolved expression in release notes')
    intro = (f'Patched llama.cpp builds from [{data["project_commit"][:12]}]'
             f'({base_url}/commit/{data["project_commit"]}).\n\n'
             f'Upstream base: `{data["upstream_commit"]}`.\n\n'
             f'Enabled patches: {", ".join(data["features"])}.\n\n'
             'TurboQuant is experimental; GPU TurboQuant support is limited to turbo4 on Vulkan. '
             'MoE expert caching defaults to off. These builds do not establish performance or model-quality results.\n\n')
    Path('release-notes.md').write_text(intro + '\n'.join(lines) + '\n\n'
                                      f'[Checksums]({base_url}/releases/download/{tag}/SHA256SUMS) · '
                                      f'[Build manifest]({base_url}/releases/download/{tag}/release-manifest.json)\n')


if __name__ == '__main__':
    main()
