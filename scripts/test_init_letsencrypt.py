#!/usr/bin/env python3
"""Static checks for init-letsencrypt.sh. Stdlib only: `python3 scripts/test_init_letsencrypt.py`."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "init-letsencrypt.sh"
COMPOSE_FILE_RE = re.compile(r'-f "\$root/([^"]+)"')
RUN_SERVICE_RE = re.compile(r'"\$\{compose\[@\]\}" (?:run|up|exec)\b.*?\b(certbot|nginx)\b', re.S)


class InitLetsencryptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SCRIPT.read_text()

    def test_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_compose_file_resolves_from_repo_root(self) -> None:
        files = COMPOSE_FILE_RE.findall(self.text)
        self.assertTrue(files, "script must pass -f \"$root/<compose file>\"")
        for rel in files:
            self.assertTrue((REPO / rel).is_file(), f"{rel} does not exist")
        self.assertNotRegex(self.text, r"-f docker-compose\.", "bare cwd-relative -f path")

    def test_targeted_services_exist(self) -> None:
        compose = (REPO / COMPOSE_FILE_RE.findall(self.text)[0]).read_text()
        for service in set(RUN_SERVICE_RE.findall(self.text)):
            self.assertRegex(compose, rf"(?m)^  {service}:$", f"no {service} service")

    def test_data_path_is_mounted(self) -> None:
        match = re.search(r'data_path="\$root/([^"]+)"', self.text)
        self.assertIsNotNone(match, "data_path must be rooted at $root")
        data_path = match.group(1)
        compose = (REPO / COMPOSE_FILE_RE.findall(self.text)[0]).read_text()
        self.assertIn(f"./{data_path}/configs/", compose)
        self.assertIn('"$data_path/configs/live/', self.text)

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck(self) -> None:
        subprocess.run(["shellcheck", str(SCRIPT)], check=True)


if __name__ == "__main__":
    unittest.main()
