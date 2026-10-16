"""Create a portable ZIP with checksums, usage notes and dependency licenses."""
import argparse
import hashlib
import importlib.metadata
import sys
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site-packages', type=Path)
    parser.add_argument('--python-license', type=Path, default=Path(sys.base_prefix) / 'LICENSE.txt')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'dist'
    exe = output / 'ModHarbor.exe'
    if not exe.is_file() or exe.read_bytes()[:2] != b'MZ':
        raise SystemExit('Build dist/ModHarbor.exe first.')
    notices = []
    if not args.python_license.is_file():
        raise SystemExit('Python LICENSE.txt is required for distribution.')
    notices.append('CPython\n' + args.python_license.read_text(encoding='utf-8', errors='replace'))
    options = {'path': [str(args.site_packages)]} if args.site_packages else {}
    for distribution in sorted(importlib.metadata.distributions(**options), key=lambda d: d.metadata['Name'].lower()):
        for file in distribution.files or []:
            path = str(file).lower()
            if '.dist-info/' not in path:
                continue
            if any(token in Path(path).name for token in ['license', 'copying', 'notice']) or '/licenses/' in path:
                actual = distribution.locate_file(file)
                if actual.is_file():
                    notices.append(f'{distribution.metadata["Name"]} {distribution.version} · {file}\n' + actual.read_text(encoding='utf-8', errors='replace'))
    (output / 'THIRD-PARTY-NOTICES.txt').write_text('\n\n' + ('\n\n' + '='*72 + '\n\n').join(notices), encoding='utf-8')
    checksum = hashlib.sha256(exe.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(f'{checksum}  ModHarbor.exe\n', encoding='ascii')
    archive = output / 'ModHarbor-0.2.0-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in ['ModHarbor.exe', 'SHA256SUMS.txt', 'THIRD-PARTY-NOTICES.txt']:
            bundle.write(output / name, name)
        bundle.write(root / 'packaging/windows/README-Windows.txt', 'README-Windows.txt')
    print(f'Created {archive.name} ({archive.stat().st_size:,} bytes)\nSHA256 EXE: {checksum}')


if __name__ == '__main__':
    main()
