import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _path  # noqa: E402,F401
import platform_utils  # noqa: E402


class PlatformUtilsTests(unittest.TestCase):
    def test_parse_connected_interfaces_keeps_multi_word_names(self):
        sample = """
Admin State    State          Type             Interface Name
-------------------------------------------------------------------------
Enabled        Connected      Dedicated        Wi-Fi
Enabled        Connected      Dedicated        Local Area Connection
Disabled       Disconnected   Dedicated        Ethernet 2
Enabled        Connected      Dedicated        vEthernet Default Switch
"""
        self.assertEqual(
            platform_utils._parse_connected_interfaces(sample),
            ["Wi-Fi", "Local Area Connection", "vEthernet Default Switch"],
        )

    def test_windows_install_service_quotes_python_and_script_paths(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(platform_utils.subprocess, "run", side_effect=fake_run):
            platform_utils._windows_install_service(
                "hide-killswitch",
                "HIDE Network Kill-Switch",
                r"C:\Users\Jane Doe\Hide\.venv\Scripts\python.exe",
                r"C:\Users\Jane Doe\Hide\core\main.py",
            )

        create_cmd = calls[0][0]
        self.assertIn("/TR", create_cmd)
        tr_value = create_cmd[create_cmd.index("/TR") + 1]
        self.assertEqual(
            tr_value,
            r'\"C:\Users\Jane Doe\Hide\.venv\Scripts\python.exe\" \"C:\Users\Jane Doe\Hide\core\main.py\"',
        )
        self.assertEqual(calls[1][0], ["schtasks", "/Run", "/TN", r"HIDE\hide-killswitch"])

    def test_brew_install_checks_intel_homebrew_path(self):
        calls = []

        def fake_isfile(path):
            return path == "/usr/local/bin/brew"

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(platform_utils.shutil, "which", return_value=None), \
             mock.patch.object(platform_utils.os.path, "isfile", side_effect=fake_isfile), \
             mock.patch.object(platform_utils.subprocess, "run", side_effect=fake_run):
            platform_utils._brew_install("tor")

        self.assertEqual(calls[0][0], ["/usr/local/bin/brew", "install", "tor"])

    def test_macos_pf_block_loads_base_then_killswitch_anchor(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd == ["pfctl", "-sr"] or cmd == ["pfctl", "-sn"]:
                return mock.Mock(returncode=0, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(platform_utils.subprocess, "run", side_effect=fake_run):
            platform_utils._macos_pf_block()

        self.assertEqual(calls[0][0], ["pfctl", "-sr"])
        self.assertEqual(calls[1][0], ["pfctl", "-sn"])
        self.assertEqual(calls[2][0], ["pfctl", "-f", "-"])
        self.assertIn('rdr-anchor "com.privacy_tool.dns"', calls[2][1]["input"])
        self.assertIn('anchor "com.privacy_tool.killswitch"', calls[2][1]["input"])
        self.assertEqual(calls[3][0], ["pfctl", "-a", "com.privacy_tool.killswitch", "-f", "-"])
        self.assertIn("block drop out quick", calls[3][1]["input"])
        self.assertEqual(calls[4][0], ["pfctl", "-e"])

    def test_macos_pf_block_skips_base_when_hide_anchors_loaded(self):
        calls = []
        sr = """
anchor "com.privacy_tool.killswitch" all
anchor "com.privacy_tool.dns" all
anchor "com.privacy_tool.telemetry" all
anchor "com.privacy_tool.ntp" all
"""
        sn = 'rdr-anchor "com.privacy_tool.dns" all\n'

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd == ["pfctl", "-sr"]:
                return mock.Mock(returncode=0, stdout=sr, stderr="")
            if cmd == ["pfctl", "-sn"]:
                return mock.Mock(returncode=0, stdout=sn, stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(platform_utils.subprocess, "run", side_effect=fake_run):
            platform_utils._macos_pf_block()

        self.assertNotIn(["pfctl", "-f", "-"], [cmd for cmd, _ in calls])
        self.assertEqual(calls[2][0], ["pfctl", "-a", "com.privacy_tool.killswitch", "-f", "-"])


if __name__ == "__main__":
    unittest.main()
