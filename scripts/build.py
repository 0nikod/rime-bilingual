#!/usr/bin/env python3
"""Build the two OpenCC dictionaries used by rime-bilingual.

Only the Python standard library is required.  OpenCC's ``opencc_dict`` command
performs compilation; when the ``opencc`` command (or a compatible optional
Python binding) is available, representative default conversions are also
checked through the generated JSON configuration.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

NBSP = "\u00a0"
DEFAULT_MAX_PARSE_ERROR_RATIO = 0.20
CEDICT_LINE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^]]*)\]\s+/(.*)/\s*$")
ENGLISH_KEY = re.compile(r"^[A-Za-z][A-Za-z'-]*$")
CEDICT_METADATA = re.compile(
    r"^(?:CL:|variant of\b|see also\b|used in\b)", re.IGNORECASE
)
CEDICT_GLOSS_SPLIT = re.compile(r"\s*;\s*")
ECDICT_POS_PREFIX = re.compile(
    r"^(?:(?:n|v|vt|vi|adj|adv|prep|pron|conj|num|art|aux|abbr|int)\.?|"
    r"(?:noun|verb|adjective|adverb|preposition|pronoun|conjunction))\s*[:.．]\s*",
    re.IGNORECASE,
)
ECDICT_SPLIT = re.compile(r"(?:\\n|\\r|[\r\n;；])+")
ECDICT_LABEL = re.compile(r"^\[[^\]\r\n]+\]\s*")
REPRESENTATIVE_KEYS = ("你好", "输入法", "study", "computer")


class BuildError(RuntimeError):
    """A user-facing, expected build failure."""


@dataclass
class ParseStats:
    source: str
    records: int = 0
    malformed: int = 0
    skipped: int = 0
    fragments: int = 0
    removed_empty: int = 0
    removed_duplicate: int = 0
    removed_long: int = 0
    removed_limited: int = 0
    removed_metadata: int = 0
    removed_invalid: int = 0

    @property
    def error_ratio(self) -> float:
        return self.malformed / self.records if self.records else 0.0


Dictionary = OrderedDict[str, list[str]]


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def warn_limited(stats: ParseStats, message: str, *, limit: int = 20) -> None:
    """Avoid flooding stderr when a large real source contains many skipped rows."""
    if stats.malformed <= limit:
        warn(message)
    elif stats.malformed == limit + 1:
        warn(f"{stats.source}: more invalid rows omitted from warning output")


def normalize_fragment(value: str) -> str:
    """Collapse Unicode whitespace and remove line/tab separators."""
    return " ".join(value.strip().split())


def valid_key(key: str) -> bool:
    return (
        bool(key)
        and "\x00" not in key
        and not any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in key)
    )


def append_values(
    entries: Dictionary,
    key: str,
    values: Iterable[str],
    *,
    max_length: int,
    max_count: int,
    stats: ParseStats | None = None,
) -> int:
    """Append cleaned values with stable de-duplication and source ordering."""
    if not valid_key(key):
        if stats is not None:
            stats.removed_invalid += 1
        return 0

    target = entries.get(key)
    added = 0
    for raw in values:
        value = normalize_fragment(raw)
        if not value:
            if stats is not None:
                stats.removed_empty += 1
            continue
        if "\x00" in value or any(ord(ch) < 0x20 for ch in value):
            if stats is not None:
                stats.removed_invalid += 1
            continue
        if len(value) > max_length:
            if stats is not None:
                stats.removed_long += 1
            continue
        if target is not None and value in target:
            if stats is not None:
                stats.removed_duplicate += 1
            continue
        if target is not None and len(target) >= max_count:
            if stats is not None:
                stats.removed_limited += 1
            continue
        if target is None:
            target = []
            entries[key] = target
        target.append(value)
        added += 1
    return added


def parse_cedict(
    path: Path | str,
    *,
    max_translation_length: int = 40,
    max_translations_per_entry: int = 6,
) -> tuple[Dictionary, ParseStats]:
    """Parse CC-CEDICT and return simplified-key English definitions."""
    source = Path(path)
    entries: Dictionary = OrderedDict()
    stats = ParseStats(str(source))
    try:
        handle = source.open("r", encoding="utf-8-sig")
    except OSError as exc:
        raise BuildError(f"cannot read CC-CEDICT source {source}: {exc}") from exc

    try:
        with handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                stats.records += 1
                match = CEDICT_LINE.fullmatch(line)
                if not match:
                    stats.malformed += 1
                    warn(f"{source}:{line_number}: malformed CC-CEDICT line")
                    continue
                simplified = match.group(2)
                definitions: list[str] = []
                for definition in match.group(4).split("/"):
                    for gloss in CEDICT_GLOSS_SPLIT.split(definition):
                        if CEDICT_METADATA.match(gloss.strip()):
                            stats.removed_metadata += 1
                        else:
                            definitions.append(gloss)
                added = append_values(
                    entries,
                    simplified,
                    definitions,
                    max_length=max_translation_length,
                    max_count=max_translations_per_entry,
                    stats=stats,
                )
                stats.fragments += added
                if not added and simplified not in entries:
                    stats.skipped += 1
    except UnicodeError as exc:
        raise BuildError(f"CC-CEDICT source is not valid UTF-8: {source}: {exc}") from exc
    return entries, stats


def split_ecdict_translation(
    translation: str, stats: ParseStats | None = None
) -> list[str]:
    """Conservatively split ECDICT translations without guessing at commas."""
    fragments: list[str] = []
    for raw in ECDICT_SPLIT.split(translation):
        fragment = normalize_fragment(raw)
        fragment = ECDICT_LABEL.sub("", fragment, count=1).strip()
        while fragment:
            stripped = ECDICT_POS_PREFIX.sub("", fragment, count=1)
            if stripped == fragment:
                break
            fragment = stripped.strip()
        if fragment:
            fragments.append(fragment)
        elif stats is not None:
            stats.removed_empty += 1
    return fragments


def parse_ecdict(
    path: Path | str,
    *,
    max_translation_length: int = 40,
    max_translations_per_entry: int = 6,
) -> tuple[Dictionary, ParseStats]:
    """Parse ECDICT CSV, accepting a UTF-8 BOM and standard CSV quoting."""
    source = Path(path)
    entries: Dictionary = OrderedDict()
    stats = ParseStats(str(source))
    try:
        handle = source.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise BuildError(f"cannot read ECDICT source {source}: {exc}") from exc

    try:
        with handle:
            reader = csv.DictReader(handle, strict=True)
            if reader.fieldnames is None:
                raise BuildError(f"ECDICT source {source} has no CSV header")
            fields = {name.strip().lower(): name for name in reader.fieldnames if name}
            if "word" not in fields or "translation" not in fields:
                raise BuildError(
                    f"ECDICT source {source} must contain word and translation columns"
                )
            for row_number, row in enumerate(reader, 2):
                stats.records += 1
                if None in row:
                    stats.malformed += 1
                    warn_limited(stats, f"{source}:{row_number}: malformed ECDICT CSV row")
                    continue
                word = normalize_fragment(row.get(fields["word"], "") or "").lower()
                translation = row.get(fields["translation"], "") or ""
                if not translation.strip():
                    stats.malformed += 1
                    warn_limited(
                        stats,
                        f"{source}:{row_number}: ECDICT row has no translation",
                    )
                    continue
                if not ENGLISH_KEY.fullmatch(word):
                    # The full ECDICT CSV deliberately contains many phrases and
                    # punctuation-heavy keys.  They are valid source records but
                    # outside the Lua filter's single-word lookup grammar.
                    stats.removed_invalid += 1
                    stats.skipped += 1
                    continue
                values = split_ecdict_translation(translation, stats)
                added = append_values(
                    entries,
                    word,
                    values,
                    max_length=max_translation_length,
                    max_count=max_translations_per_entry,
                    stats=stats,
                )
                stats.fragments += added
                if not added and word not in entries:
                    stats.skipped += 1
    except csv.Error as exc:
        raise BuildError(f"cannot parse ECDICT CSV {source}: {exc}") from exc
    except UnicodeError as exc:
        raise BuildError(f"ECDICT source is not valid UTF-8: {source}: {exc}") from exc
    return entries, stats


def check_parse_ratio(stats: ParseStats) -> None:
    """Reject inputs that look like the wrong format instead of silently shrinking."""
    if stats.records == 0:
        raise BuildError(f"source contains no data records: {stats.source}")
    if stats.error_ratio > DEFAULT_MAX_PARSE_ERROR_RATIO:
        raise BuildError(
            f"parse error ratio for {stats.source} is {stats.error_ratio:.1%}; "
            f"limit is {DEFAULT_MAX_PARSE_ERROR_RATIO:.0%}"
        )


def encoded_lines(entries: Dictionary) -> list[str]:
    """Produce OpenCC text dictionary lines sorted by unique key."""
    lines: list[str] = []
    for key in sorted(entries):
        values = entries[key]
        if not valid_key(key) or not values:
            raise BuildError(f"invalid dictionary entry for key {key!r}")
        encoded: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = normalize_fragment(value)
            if (
                not clean
                or "\x00" in clean
                or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in clean)
            ):
                raise BuildError(f"invalid dictionary value for key {key!r}")
            token = clean.replace(" ", NBSP)
            if token in seen:
                raise BuildError(f"duplicate dictionary value for key {key!r}")
            seen.add(token)
            encoded.append(token)
        lines.append(f"{key}\t{' '.join(encoded)}")
    return lines


def write_text_dictionary(path: Path, entries: Dictionary) -> None:
    lines = encoded_lines(entries)
    if not lines:
        raise BuildError(f"refusing to write empty dictionary: {path}")
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise BuildError(f"cannot write dictionary {path}: {exc}") from exc


def opencc_config(filename: str, name: str) -> dict[str, object]:
    """Return the deliberately segmentation-free exact dictionary config."""
    return {
        "name": name,
        "conversion_chain": [
            {"dict": {"type": "ocd2", "file": filename}},
        ],
    }


def write_opencc_config(path: Path, dictionary_filename: str, name: str) -> None:
    try:
        path.write_text(
            json.dumps(
                opencc_config(dictionary_filename, name),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise BuildError(f"cannot write OpenCC config {path}: {exc}") from exc


def run_opencc_dict(
    tool: str, source: Path, destination: Path, from_: str = "text", to: str = "ocd2"
) -> None:
    try:
        subprocess.run(
            [tool, "-i", str(source), "-o", str(destination), "-f", from_, "-t", to],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"opencc_dict failed for {source.name}: {exc}") from exc


def read_text_dictionary(path: Path) -> dict[str, list[str]]:
    """Read and rigorously validate the generated OpenCC text format."""
    parsed: dict[str, list[str]] = {}
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise BuildError(f"cannot validate dictionary {path}: {exc}") from exc
    if not raw or not text.endswith("\n") or "\r" in text or "\x00" in text:
        raise BuildError(f"invalid encoding or line endings in dictionary {path}")

    previous: str | None = None
    for number, line in enumerate(text[:-1].split("\n"), 1):
        if not line or line.count("\t") != 1:
            raise BuildError(f"invalid OpenCC text dictionary line {path}:{number}")
        key, raw_values = line.split("\t", 1)
        values = raw_values.split(" ")
        if (
            not valid_key(key)
            or not values
            or any(
                not value
                or "\t" in value
                or "\n" in value
                or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)
                for value in values
            )
            or len(values) != len(set(values))
        ):
            raise BuildError(f"invalid OpenCC text dictionary line {path}:{number}")
        if previous is not None and key <= previous:
            raise BuildError(f"dictionary keys are not strictly sorted at {path}:{number}")
        previous = key
        parsed[key] = values
    if not parsed:
        raise BuildError(f"dictionary contains no entries: {path}")
    return parsed


def validate_json_config(path: Path, dictionary_filename: str, name: str) -> None:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot load generated OpenCC config {path}: {exc}") from exc
    if config != opencc_config(dictionary_filename, name):
        raise BuildError(f"generated OpenCC config has an unexpected structure: {path}")


def representative_items(entries: dict[str, list[str]]) -> list[tuple[str, str]]:
    keys = [key for key in REPRESENTATIVE_KEYS if key in entries]
    if not keys:
        keys = list(entries)[:2]
    return [(key, entries[key][0]) for key in keys]


def validate_with_opencc_cli(
    tool: str, config_path: Path, entries: dict[str, list[str]]
) -> None:
    """Load the JSON and check OpenCC's default value for representative keys."""
    items = representative_items(entries)
    with tempfile.TemporaryDirectory(prefix="rime-bilingual-opencc-") as temporary:
        input_path = Path(temporary) / "input.txt"
        output_path = Path(temporary) / "output.txt"
        input_path.write_text(
            "\n".join(key for key, _ in items) + "\n", encoding="utf-8"
        )
        try:
            subprocess.run(
                [
                    tool,
                    "-c",
                    config_path.name,
                    "-i",
                    str(input_path),
                    "-o",
                    str(output_path),
                ],
                cwd=config_path.parent,
                check=True,
            )
            actual = output_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
            raise BuildError(
                f"opencc failed to load/validate {config_path.name}: {exc}"
            ) from exc
    expected = [value for _, value in items]
    if actual != expected:
        details = ", ".join(
            f"{key!r}->{value.replace(NBSP, ' ')!r}" for key, value in items
        )
        raise BuildError(
            f"OpenCC default conversion mismatch for {config_path.name}; expected {details}"
        )


def validate_with_python_binding(
    config_path: Path, entries: dict[str, list[str]]
) -> bool:
    """Try a compatible optional ``opencc`` binding; return False if unavailable."""
    try:
        module = importlib.import_module("opencc")
    except ImportError:
        return False
    constructor = getattr(module, "OpenCC", None)
    if constructor is None:
        return False
    try:
        converter = constructor(str(config_path))
        actual = [converter.convert(key) for key, _ in representative_items(entries)]
    except Exception as exc:  # Binding APIs/errors are outside this stdlib tool.
        raise BuildError(
            f"Python OpenCC binding failed to load/validate {config_path.name}: {exc}"
        ) from exc
    expected = [value for _, value in representative_items(entries)]
    if actual != expected:
        raise BuildError(f"OpenCC default conversion mismatch for {config_path.name}")
    return True


def validate_compiled(
    compiled_path: Path,
    config_path: Path,
    text_path: Path,
    *,
    name: str,
    opencc_cli: str | None,
) -> str:
    """Validate source/config/artifact without unreliable ocd2-to-text conversion."""
    if not compiled_path.is_file() or compiled_path.stat().st_size == 0:
        raise BuildError(f"compiled dictionary is absent or empty: {compiled_path}")
    entries = read_text_dictionary(text_path)
    validate_json_config(config_path, compiled_path.name, name)
    if opencc_cli:
        validate_with_opencc_cli(opencc_cli, config_path, entries)
        return "opencc CLI default-conversion check"
    if validate_with_python_binding(config_path, entries):
        return "Python OpenCC default-conversion check"
    warn(
        "opencc CLI/Python binding not found; validation is limited to rigorous "
        "text/config checks and a nonempty compiled artifact"
    )
    return "portable artifact fallback (OpenCC runtime unavailable)"


def print_stats(label: str, stats: ParseStats) -> None:
    print(
        f"{label}: records={stats.records} malformed={stats.malformed} "
        f"skipped_records={stats.skipped} accepted_translations={stats.fragments}"
    )
    print(
        "  removed: "
        f"empty={stats.removed_empty} duplicate={stats.removed_duplicate} "
        f"long={stats.removed_long} limited={stats.removed_limited} "
        f"metadata={stats.removed_metadata} invalid={stats.removed_invalid}"
    )


def build(
    cedict: Path | str,
    ecdict: Path | str,
    output: Path | str,
    *,
    max_translation_length: int = 40,
    max_translations_per_entry: int = 6,
    opencc_dict: str | None = None,
    opencc_cli: str | None = None,
) -> dict[str, object]:
    if max_translation_length < 1 or max_translations_per_entry < 1:
        raise BuildError("translation length and count limits must be positive")

    dictionary_tool = opencc_dict or shutil.which("opencc_dict")
    if not dictionary_tool:
        raise BuildError("opencc_dict was not found in PATH")
    cli_tool = shutil.which("opencc") if opencc_cli is None else opencc_cli

    zh_entries, cedict_stats = parse_cedict(
        cedict,
        max_translation_length=max_translation_length,
        max_translations_per_entry=max_translations_per_entry,
    )
    en_entries, ecdict_stats = parse_ecdict(
        ecdict,
        max_translation_length=max_translation_length,
        max_translations_per_entry=max_translations_per_entry,
    )
    check_parse_ratio(cedict_stats)
    check_parse_ratio(ecdict_stats)
    if not zh_entries:
        raise BuildError("CC-CEDICT produced zero zh-to-en entries")
    if not en_entries:
        raise BuildError("ECDICT produced zero en-to-zh entries")

    output_path = Path(output)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BuildError(f"cannot create output directory {output_path}: {exc}") from exc

    products = {
        "zh_to_en": (
            output_path / "bilingual_zh_en.txt",
            output_path / "bilingual_zh_en.ocd2",
            output_path / "bilingual_zh_en.json",
            zh_entries,
            "Chinese to English bilingual hints",
        ),
        "en_to_zh": (
            output_path / "bilingual_en_zh.txt",
            output_path / "bilingual_en_zh.ocd2",
            output_path / "bilingual_en_zh.json",
            en_entries,
            "English to Chinese bilingual hints",
        ),
    }
    validations: dict[str, str] = {}
    for direction, product in products.items():
        text_path, compiled_path, config_path, entries, name = product
        write_text_dictionary(text_path, entries)
        # Re-read before compilation so malformed/unsorted compiler input never passes.
        read_text_dictionary(text_path)
        write_opencc_config(config_path, compiled_path.name, name)
        validate_json_config(config_path, compiled_path.name, name)
        run_opencc_dict(dictionary_tool, text_path, compiled_path)
        validations[direction] = validate_compiled(
            compiled_path,
            config_path,
            text_path,
            name=name,
            opencc_cli=cli_tool,
        )

    print("== Sources and filtering ==")
    print_stats("CC-CEDICT", cedict_stats)
    print_stats("ECDICT", ecdict_stats)
    print("== Directions ==")
    print(
        f"zh_to_en: keys={len(zh_entries)} "
        f"translations={sum(map(len, zh_entries.values()))}"
    )
    print(
        f"en_to_zh: keys={len(en_entries)} "
        f"translations={sum(map(len, en_entries.values()))}"
    )
    print("== Validation ==")
    for direction, method in validations.items():
        print(f"{direction}: {method}")
    print("== Files ==")
    for product in products.values():
        for path in product[:3]:
            print(f"{path}: {path.stat().st_size} bytes")

    return {
        "cedict": cedict_stats,
        "ecdict": ecdict_stats,
        "zh_entries": zh_entries,
        "en_entries": en_entries,
        "output": output_path,
        "validations": validations,
    }


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build zh-to-en and en-to-zh OpenCC dictionaries in one invocation."
    )
    parser.add_argument("--cedict", required=True, type=Path, help="CC-CEDICT text file")
    parser.add_argument("--ecdict", required=True, type=Path, help="ECDICT CSV file")
    parser.add_argument("--output", required=True, type=Path, help="output directory")
    parser.add_argument(
        "--max-translation-length",
        type=int,
        default=40,
        help="maximum Unicode codepoints per translation (default: 40)",
    )
    parser.add_argument(
        "--max-translations-per-entry",
        type=int,
        default=6,
        help="maximum translations retained per key (default: 6)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = argument_parser().parse_args(argv)
    try:
        build(
            args.cedict,
            args.ecdict,
            args.output,
            max_translation_length=args.max_translation_length,
            max_translations_per_entry=args.max_translations_per_entry,
        )
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
