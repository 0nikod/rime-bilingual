from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bilingual_fetch_build", ROOT / "scripts" / "fetch_and_build.py"
)
assert SPEC and SPEC.loader
fetch_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fetch_module
SPEC.loader.exec_module(fetch_module)


class PublishTests(unittest.TestCase):
    @staticmethod
    def populate(directory: Path, prefix: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name in fetch_module.PRODUCTS:
            (directory / name).write_text(f"{prefix}:{name}\n", encoding="utf-8")

    def test_publish_replaces_complete_product_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            output = root / "output"
            self.populate(staging, "new")
            self.populate(output, "old")

            fetch_module.publish(staging, output)

            for name in fetch_module.PRODUCTS:
                self.assertEqual(
                    (output / name).read_text(encoding="utf-8"),
                    f"new:{name}\n",
                )

    def test_publish_rolls_back_if_installation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            output = root / "output"
            self.populate(staging, "new")
            self.populate(output, "old")
            original_replace = fetch_module.os.replace
            failing_name = fetch_module.PRODUCTS[2]

            def replace_with_failure(source: object, destination: object) -> None:
                source_path = Path(source)
                if source_path.parent == staging and source_path.name == failing_name:
                    raise OSError("simulated publish failure")
                original_replace(source, destination)

            with mock.patch.object(
                fetch_module.os, "replace", side_effect=replace_with_failure
            ):
                with self.assertRaises(OSError):
                    fetch_module.publish(staging, output)

            for name in fetch_module.PRODUCTS:
                self.assertEqual(
                    (output / name).read_text(encoding="utf-8"),
                    f"old:{name}\n",
                )


if __name__ == "__main__":
    unittest.main()
