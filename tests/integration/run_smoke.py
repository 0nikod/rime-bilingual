#!/usr/bin/env python3
"""Run a self-contained candidate-level librime/librime-lua smoke test."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "integration"


def find_lua_plugin() -> Path:
    candidates = [
        Path("/usr/lib/rime-plugins/librime-lua.so"),
        Path("/usr/lib/x86_64-linux-gnu/rime-plugins/librime-lua.so"),
        Path("/usr/lib/aarch64-linux-gnu/rime-plugins/librime-lua.so"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("librime-lua shared plugin was not found")


def shared_data_dir() -> Path:
    override = os.environ.get("RIME_SHARED_DATA_DIR")
    candidates = [Path(override)] if override else []
    candidates.extend((Path("/usr/share/rime-data"), Path("/usr/share/rime")))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Rime shared data directory was not found")


def run() -> None:
    compiler = shutil.which("g++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("a C++ compiler is required")
    plugin = find_lua_plugin()

    with tempfile.TemporaryDirectory(prefix="rime-bilingual-smoke-") as temporary:
        base = Path(temporary)
        user = base / "user"
        binary = base / "rime-smoke"
        (user / "lua").mkdir(parents=True)
        (user / "opencc").mkdir(parents=True)

        shutil.copy2(ROOT / "lua" / "bilingual_hint.lua", user / "lua")
        shutil.copy2(FIXTURE / "candidate_source.lua", user / "lua")
        shutil.copy2(FIXTURE / "bilingual_smoke.schema.yaml", user)
        shutil.copy2(FIXTURE / "bilingual_smoke_all.schema.yaml", user)
        shutil.copy2(FIXTURE / "bilingual_smoke_random.schema.yaml", user)
        shutil.copy2(FIXTURE / "default.yaml", user)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build.py"),
                "--cedict",
                str(ROOT / "tests" / "fixtures" / "cedict_sample.txt"),
                "--ecdict",
                str(ROOT / "tests" / "fixtures" / "ecdict_sample.csv"),
                "--output",
                str(user / "opencc"),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        subprocess.run(
            [
                compiler,
                "-std=c++11",
                str(FIXTURE / "rime_smoke.cc"),
                "-o",
                str(binary),
                "-Wl,--no-as-needed",
                f"-Wl,-rpath,{plugin.parent}",
                str(plugin),
                "-lrime",
            ],
            check=True,
        )
        environment = os.environ.copy()
        current_library_path = environment.get("LD_LIBRARY_PATH", "")
        environment["LD_LIBRARY_PATH"] = str(plugin.parent) + (
            os.pathsep + current_library_path if current_library_path else ""
        )
        subprocess.run(
            [str(binary), str(user), str(shared_data_dir())],
            env=environment,
            check=True,
        )

        shutil.rmtree(user / "opencc")
        (user / "opencc").mkdir()
        for asset in (ROOT / "opencc").iterdir():
            if asset.suffix in {".json", ".ocd2"}:
                shutil.copy2(asset, user / "opencc")
        subprocess.run(
            [str(binary), str(user), str(shared_data_dir()), "release"],
            env=environment,
            check=True,
        )


if __name__ == "__main__":
    try:
        run()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1)
