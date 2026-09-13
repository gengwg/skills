#!/usr/bin/env python3
"""Tests for rm_guard. Run: python3 hooks/test_guard.py"""
import json, os, subprocess, sys, unittest

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py")


def decide(command, cwd="/home/user/proj"):
    """Run the hook and return its permissionDecision, or None if it stayed silent."""
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, timeout=15)
    if not p.stdout.strip():
        return None
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


class RmGuard(unittest.TestCase):
    def test_rf_outside_scratch_asks(self):
        self.assertEqual(decide("rm -rf /home/user/proj/build"), "ask")

    def test_rf_in_scratch_is_silent(self):
        self.assertIsNone(decide("rm -rf /tmp/claude/sess/tmpdir"))

    def test_rf_in_worktree_is_silent(self):
        self.assertIsNone(decide("rm -rf /home/user/worktrees/feat"))

    def test_rf_variable_path_asks(self):
        self.assertEqual(decide("rm -rf $BUILD_DIR"), "ask")

    def test_plain_rm_f_is_silent(self):
        self.assertIsNone(decide("rm -f build/output.bin"))

    def test_rm_f_on_hyphen_r_path_is_silent(self):
        # regression: "alert-relay" contains "-r", which used to read as the -r flag
        self.assertIsNone(decide("rm -f alert-relay/alert-relay demo-app/demo-app"))

    def test_rm_r_without_force_is_silent(self):
        self.assertIsNone(decide("rm -r /home/user/proj/stale"))


if __name__ == "__main__":
    unittest.main()
