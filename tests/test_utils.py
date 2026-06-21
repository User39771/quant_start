from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aq_factor_lab.utils import load_env_file


class EnvFileTests(unittest.TestCase):
    def test_load_env_file_sets_missing_values_without_overriding_existing(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "DB_HOST=1.2.3.4",
                        "DB_PORT='5432'",
                        'DB_NAME="deeppivot"',
                    ]
                ),
                encoding="utf-8",
            )
            old = {key: os.environ.get(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME"]}
            try:
                os.environ["DB_HOST"] = "existing"
                os.environ.pop("DB_PORT", None)
                os.environ.pop("DB_NAME", None)

                load_env_file(path)

                self.assertEqual(os.environ["DB_HOST"], "existing")
                self.assertEqual(os.environ["DB_PORT"], "5432")
                self.assertEqual(os.environ["DB_NAME"], "deeppivot")
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
