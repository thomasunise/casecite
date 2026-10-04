#!/usr/bin/env python3
"""
Regenerate NOTICE.md from the dependency sets that actually ship.

Python: every package pinned in backend/requirements.lock (the hash-pinned set
the Docker image installs), with license metadata from the PyPI JSON API.
Frontend: every production (non-dev) package in frontend/package-lock.json.

Run after any dependency change:
    python3 scripts/generate_notice.py            # rewrite NOTICE.md
    python3 scripts/generate_notice.py --check    # exit 1 if NOTICE.md is stale

Needs network access to pypi.org. Standard library only.
"""

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "backend" / "requirements.lock"
PACKAGE_LOCK = ROOT / "frontend" / "package-lock.json"
NOTICE = ROOT / "NOTICE.md"

# Licences that may not be bundled with an Elastic License 2.0 distribution.
FORBIDDEN = ("AGPL", "SSPL", "GPL")
# ...except these, which contain "GPL" but are acceptable: LGPL libraries used
# unmodified as dynamically linked dependencies.
ALLOWED_GPL_FAMILY = ("LGPL",)

# Packages whose PyPI `license` field is the full license text rather than a
# name, so nothing short can be derived from the metadata.
LICENSE_OVERRIDES = {
    "tiktoken": "MIT",
}

HEADER = """# Third-party notices

CaseCite is licensed under the Elastic License 2.0 (see `LICENSE`). It is built
on the open-source packages below, each distributed under its own license.
This file lists every package and its license; it does not reproduce the
license texts. Those ship with the packages themselves: inside the Docker
image under each Python package's `*.dist-info` directory, and in each
frontend package's repository (linked below).

This file is generated — do not edit it by hand. Regenerate it whenever
`backend/requirements.lock` or `frontend/package-lock.json` changes:

```bash
python3 scripts/generate_notice.py
```

No dependency is distributed under GPL, AGPL or SSPL. `psycopg2-binary` is LGPL
and is used unmodified as a dynamically linked library. PyMuPDF (AGPL) is
deliberately not a dependency (see `backend/requirements.txt`).
"""

FOOTER = """
## System packages (Docker image)

The image is built on `python:3.11-slim` (Debian) and installs nginx, curl,
gosu, libmagic, libffi and tesseract-ocr from the Debian archive. Each is
distributed under its own license; the copyright and license files are inside
the image at `/usr/share/doc/<package>/copyright`.

## Fonts

Inter, JetBrains Mono and Source Serif 4 are distributed under the SIL Open
Font License 1.1.
"""


def locked_python_packages() -> list[tuple[str, str]]:
    """(name, version) for every pin in requirements.lock."""
    pins = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line)
        if match:
            pins.append((match.group(1), match.group(2)))
    return pins


def _short(text: str | None) -> str | None:
    """A license field is usable only if it is a name, not a pasted license text."""
    if not text:
        return None
    text = text.strip()
    if not text or "\n" in text or len(text) > 60:
        return None
    return text


def pypi_metadata(pin: tuple[str, str]) -> tuple[str, str, str, str]:
    name, version = pin
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310  # nosec B310 - fixed https host
        info = json.load(response)["info"]
    classifiers = [
        c.split(" :: ")[-1] for c in info.get("classifiers") or [] if c.startswith("License ::")
    ]
    license_name = (
        LICENSE_OVERRIDES.get(name)
        or _short(info.get("license_expression"))
        or _short(info.get("license"))
        or (" AND ".join(classifiers) if classifiers else None)
        or "See project page"
    )
    urls = info.get("project_urls") or {}
    homepage = (
        info.get("home_page")
        or urls.get("Homepage")
        or urls.get("Repository")
        or urls.get("Source")
        or f"https://pypi.org/project/{name}/"
    )
    return name, version, license_name, homepage


def frontend_packages() -> list[tuple[str, str, str, str]]:
    """Production packages from package-lock.json (lockfile v3 carries licenses)."""
    packages = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))["packages"]
    rows = set()
    for path, meta in packages.items():
        if not path or meta.get("dev"):
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        rows.add(
            (
                name,
                meta.get("version", ""),
                meta.get("license") or "See project page",
                f"https://www.npmjs.com/package/{name}",
            )
        )
    return sorted(rows, key=lambda r: (r[0].lower(), r[1]))


def table(rows: list[tuple[str, str, str, str]]) -> str:
    lines = ["| Package | Version | License |", "|---|---|---|"]
    for name, version, license_name, url in rows:
        license_name = license_name.replace("|", "/")
        lines.append(f"| [{name}]({url}) | {version} | {license_name} |")
    return "\n".join(lines)


def forbidden(rows: list[tuple[str, str, str, str]]) -> list[str]:
    bad = []
    for name, version, license_name, _ in rows:
        upper = license_name.upper()
        for marker in ALLOWED_GPL_FAMILY:
            upper = upper.replace(marker, "")
        if any(marker in upper for marker in FORBIDDEN):
            bad.append(f"{name} {version}: {license_name}")
    return bad


def build() -> tuple[str, list[str]]:
    pins = locked_python_packages()
    with ThreadPoolExecutor(max_workers=8) as pool:
        python_rows = sorted(pool.map(pypi_metadata, pins), key=lambda r: r[0].lower())
    npm_rows = frontend_packages()
    text = (
        HEADER
        + "\n## Python (backend image)\n\n"
        + f"{len(python_rows)} packages pinned in `backend/requirements.lock`. The lock is\n"
        + "universal, so it includes a few packages that install only on some platforms.\n\n"
        + table(python_rows)
        + "\n\n## JavaScript (frontend bundle)\n\n"
        + f"{len(npm_rows)} production packages in `frontend/package-lock.json`.\n\n"
        + table(npm_rows)
        + "\n"
        + FOOTER
    )
    return text, forbidden(python_rows) + forbidden(npm_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate NOTICE.md from the lock files")
    parser.add_argument(
        "--check", action="store_true", help="Do not write; exit 1 if NOTICE.md is out of date"
    )
    args = parser.parse_args()

    text, bad = build()
    if bad:
        print("ERROR: dependencies with a license that cannot ship under ELv2:")
        for entry in bad:
            print(f"  - {entry}")
        sys.exit(1)

    if args.check:
        current = NOTICE.read_text(encoding="utf-8") if NOTICE.exists() else ""
        if current != text:
            print("NOTICE.md is out of date - run: python3 scripts/generate_notice.py")
            sys.exit(1)
        print("NOTICE.md is up to date")
        return

    NOTICE.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {NOTICE}")


if __name__ == "__main__":
    main()
