"""The idle watchdog that stops CAM2 once no tab is open, including after
the computer has been asleep, and how a double-click starts the Mac app.

Run:  python -m unittest tests.test_launcher
"""

import contextlib
import io
import unittest
from unittest import mock

import launcher


class FakeState:
    def __init__(self, last_heartbeat=0.0):
        self.last_heartbeat = last_heartbeat


def watch(times, idle=600):
    """Run the watchdog over a list of clock readings; return the reading at
    which it stopped CAM2, or None if it never did."""
    readings = iter(times)
    now = [None]

    def clock():
        now[0] = next(readings)
        return now[0]

    stopped = []
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            launcher.watch_idle(FakeState(), idle, lambda: stopped.append(now[0]),
                                clock=clock, sleep=lambda _s: None)
        except StopIteration:
            pass
    return stopped[0] if stopped else None


class MacDoubleClickTests(unittest.TestCase):
    def start(self, platform, frozen, argv):
        with mock.patch.object(launcher.sys, "platform", platform), \
                mock.patch.object(launcher.pickers, "_frozen", return_value=frozen), \
                mock.patch.object(launcher.sys, "argv", argv), \
                mock.patch.object(launcher.sys, "executable", "/app/cam2"), \
                mock.patch.object(launcher.subprocess, "Popen") as popen:
            return launcher.start_in_background_if_mac_double_click(), popen

    def test_a_double_click_hands_over_to_a_child_that_stays(self):
        started, popen = self.start("darwin", True, ["/app/cam2"])
        self.assertTrue(started)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "/app/cam2")
        self.assertTrue(command[1:], "the child needs an argument, or it would hand over again")

    def test_only_the_packaged_mac_app_with_no_arguments_does(self):
        for platform, frozen, argv in (("darwin", True, ["/app/cam2", "--idle", "600"]),
                                       ("darwin", False, ["launcher.py"]),
                                       ("win32", True, ["cam2.exe"])):
            started, popen = self.start(platform, frozen, argv)
            self.assertFalse(started)
            popen.assert_not_called()


class WatchdogTests(unittest.TestCase):
    def test_stops_when_no_tab_is_open(self):
        self.assertEqual(watch(range(0, 2000, 30)), 630)

    def test_waking_from_sleep_restarts_the_wait(self):
        # Checks every 30 s, then the lid is closed for 15 minutes.
        times = [0, 30, 60, 960] + list(range(990, 3000, 30))
        self.assertEqual(watch(times), 960 + 630)


if __name__ == "__main__":
    unittest.main()
