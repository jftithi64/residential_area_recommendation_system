"""Every picture the site refers to must exist, so a missing file never shows as a broken image."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = {m for f in [*ROOT.glob("*.py"), *(ROOT / "views").glob("*.py")]
         for m in re.findall(r'["\']([\w]+\.(?:svg|png))["\']', f.read_text(encoding="utf-8"))}


class AssetsExist(unittest.TestCase):
    def test_referenced_files_exist(self):
        self.assertTrue(NAMES)
        for n in NAMES:
            self.assertTrue((ROOT / "assets" / n).exists(), n)

    def test_three_flat_placeholders(self):
        for i in range(3):
            self.assertTrue((ROOT / "assets" / f"flat_placeholder_{i}.svg").exists())


if __name__ == "__main__":
    unittest.main()
