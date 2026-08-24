#!/usr/bin/env python3
"""Download dictionary source files on demand, then build OpenCC assets."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CEDICT_URL = (
    "https://www.mdbg.net/chinese/export/cedict/"
    "cedict_1_0_ts_utf-8_mdbg.zip"
)
DEFAULT_ECDICT_URL = (
    "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"
)
PRODUCTS = (
    "bilingual_zh_en.txt",
    "bilingual_zh_en.json",
    "bilingual_zh_en.ocd2",
    "bilingual_en_zh.txt",
    "bilingual_en_zh.json",
    "bilingual_en_zh.ocd2",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch CC-CEDICT and ECDICT source files and invoke scripts/build.py. "
            "Existing downloads are reused unless --force-download is supplied."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ROOT / ".cache" / "dictionaries",
        help="download/extraction directory (default: .cache/dictionaries)",
    )
    parser.add_argument(
        "--output",
        "--output-dir",
        dest="output",
        type=Path,
        default=ROOT / "opencc",
        help="OpenCC output directory (default: opencc)",
    )
    parser.add_argument("--cedict-url", default=DEFAULT_CEDICT_URL)
    parser.add_argument("--ecdict-url", default=DEFAULT_ECDICT_URL)
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="replace cached downloads; this is manual, not an auto-update mode",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="do not access the network; require cached source files",
    )
    parser.add_argument(
        "--max-translation-length",
        type=int,
        default=40,
        help="forwarded to scripts/build.py",
    )
    parser.add_argument(
        "--max-translations-per-entry",
        type=int,
        default=6,
        help="forwarded to scripts/build.py",
    )
    return parser.parse_args()


def download(url: str, destination: Path, *, force: bool, offline: bool) -> Path:
    if destination.is_file() and not force:
        print(f"reuse {destination}")
        return destination
    if offline:
        raise RuntimeError(f"missing cached source file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    print(f"download {url}", flush=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "rime-bilingual-source-fetcher/1"},
    )
    try:
        with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def safe_extract_cedict(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as zipped:
        files = [info for info in zipped.infolist() if not info.is_dir()]
        matches = [info for info in files if Path(info.filename).name == "cedict_ts.u8"]
        if len(matches) != 1:
            names = ", ".join(info.filename for info in files)
            raise RuntimeError(
                "CC-CEDICT archive must contain exactly one cedict_ts.u8; "
                f"found: {names or '<none>'}"
            )
        member = matches[0]
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".part")
        temporary.unlink(missing_ok=True)
        with zipped.open(member) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        temporary.replace(destination)
    return destination


def validate_ecdict(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        header = source.readline().rstrip("\r\n")
    columns = {item.strip() for item in header.split(",")}
    if not {"word", "translation"}.issubset(columns):
        raise RuntimeError(f"unexpected ECDICT CSV header in {path}")


def filename_from_url(url: str, fallback: str) -> str:
    return Path(urlparse(url).path).name or fallback


def publish(staging: Path, output: Path) -> None:
    """Replace the complete product set, rolling back if a rename fails."""
    for name in PRODUCTS:
        source = staging / name
        if not source.is_file() or source.stat().st_size == 0:
            raise RuntimeError(f"build did not produce a nonempty {name}")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="rime-bilingual-backup-", dir=output.parent
    ) as temporary:
        backup = Path(temporary)
        installed: list[Path] = []
        saved: list[tuple[Path, Path]] = []
        try:
            for name in PRODUCTS:
                destination = output / name
                if destination.exists():
                    old = backup / name
                    os.replace(destination, old)
                    saved.append((old, destination))
            for name in PRODUCTS:
                destination = output / name
                os.replace(staging / name, destination)
                installed.append(destination)
        except BaseException:
            for path in installed:
                path.unlink(missing_ok=True)
            for old, destination in saved:
                if old.exists():
                    os.replace(old, destination)
            raise


def run() -> None:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output.resolve()
    source_dir.mkdir(parents=True, exist_ok=True)

    cedict_archive = download(
        args.cedict_url,
        source_dir / filename_from_url(args.cedict_url, "cedict.zip"),
        force=args.force_download,
        offline=args.no_download,
    )
    cedict_source = safe_extract_cedict(
        cedict_archive,
        source_dir / "cedict_ts.u8",
    )
    ecdict_source = download(
        args.ecdict_url,
        source_dir / filename_from_url(args.ecdict_url, "ecdict.csv"),
        force=args.force_download,
        offline=args.no_download,
    )
    validate_ecdict(ecdict_source)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="rime-bilingual-build-", dir=output_dir.parent
    ) as temporary:
        staging = Path(temporary)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "build.py"),
            "--cedict",
            str(cedict_source),
            "--ecdict",
            str(ecdict_source),
            "--output",
            str(staging),
            "--max-translation-length",
            str(args.max_translation_length),
            "--max-translations-per-entry",
            str(args.max_translations_per_entry),
        ]
        print("build " + " ".join(command[2:]), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
        publish(staging, output_dir)


if __name__ == "__main__":
    try:
        run()
    except (OSError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"fetch/build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
