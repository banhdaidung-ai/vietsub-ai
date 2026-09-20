"""
tests/test_platform_helper.py — Kiểm thử các tính năng ẩn cửa sổ console trên Windows
"""

import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.platform_helper import get_subprocess_no_window_kwargs, run_hidden_subprocess


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = 0


class TestPlatformHelper(unittest.TestCase):
    def test_subprocess_no_window_kwargs_on_current_platform(self):
        kwargs = get_subprocess_no_window_kwargs()
        if sys.platform == "win32":
            self.assertIn("creationflags", kwargs)
            self.assertEqual(kwargs["creationflags"], 0x08000000)
            self.assertIn("startupinfo", kwargs)
            self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)
        else:
            self.assertEqual(kwargs, {})

    @patch("sys.platform", "win32")
    def test_subprocess_no_window_kwargs_mocked_windows(self):
        with patch.object(subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             patch.object(subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             patch.object(subprocess, "SW_HIDE", 0, create=True), \
             patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            kwargs = get_subprocess_no_window_kwargs()
            self.assertIn("creationflags", kwargs)
            self.assertEqual(kwargs["creationflags"], 0x08000000)
            self.assertIn("startupinfo", kwargs)
            self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)
            self.assertEqual(kwargs["startupinfo"].dwFlags, 1)

    def test_run_hidden_subprocess_executes_successfully(self):
        res = run_hidden_subprocess(
            [sys.executable, "-c", "import sys; sys.stdout.write('no_window_ok')"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "no_window_ok")

    @patch("sys.platform", "win32")
    @patch("subprocess.run")
    def test_run_hidden_subprocess_injects_win32_flags(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=["test"], returncode=0)

        with patch.object(subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             patch.object(subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             patch.object(subprocess, "SW_HIDE", 0, create=True), \
             patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            run_hidden_subprocess(["test_cmd"], capture_output=True)

            self.assertTrue(mock_run.called)
            _, kwargs = mock_run.call_args
            self.assertIn("creationflags", kwargs)
            self.assertEqual(kwargs["creationflags"], 0x08000000)
            self.assertIn("startupinfo", kwargs)
            self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)
            self.assertTrue(kwargs["capture_output"])


if __name__ == "__main__":
    unittest.main()
