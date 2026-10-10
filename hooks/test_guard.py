#!/usr/bin/env python3
"""Tests for guard.py. Run: python3 hooks/test_guard.py"""
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


TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def repo(tmp, remote, message="fix thing"):
    """A repo on a feature branch with one local commit and one remote."""
    run = lambda *a: subprocess.run(["git", "-C", tmp, "-c", "commit.gpgsign=false", *a],
                                    check=True, capture_output=True)
    run("init", "-q", "-b", "fix-branch")
    run("remote", "add", "upstream", remote)
    run("commit", "-q", "--allow-empty", "-m", message)
    return tmp


class ClaGuard(unittest.TestCase):
    K8S = "https://github.com/kubernetes-sigs/kubespray.git"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_commit_with_trailer_in_k8s_repo_denied(self):
        d = repo(self.tmp, self.K8S)
        self.assertEqual(decide(f'git commit -m "fix\n\n{TRAILER}"', d), "deny")

    def test_heredoc_commit_message_denied(self):
        d = repo(self.tmp, "git@github.com:kubernetes/website.git")
        cmd = f"git commit -m \"$(cat <<'EOF'\nfix\n\n{TRAILER}\nEOF\n)\""
        self.assertEqual(decide(cmd, d), "deny")

    def test_commit_with_trailer_elsewhere_is_silent(self):
        d = repo(self.tmp, "https://github.com/gengwg/skills.git")
        self.assertIsNone(decide(f'git commit -m "fix\n\n{TRAILER}"', d))

    def test_commit_without_trailer_is_silent(self):
        d = repo(self.tmp, self.K8S)
        self.assertIsNone(decide('git commit -m "fix\n\nSigned-off-by: Dev <dev@example.com>"', d))

    def test_amend_that_strips_trailer_is_silent(self):
        d = repo(self.tmp, self.K8S)
        cmd = "git commit --amend -m \"$(git log -1 --format=%B | grep -v '^Co-Authored-By:')\""
        self.assertIsNone(decide(cmd, d))

    def test_push_of_unpushed_trailer_commit_denied(self):
        d = repo(self.tmp, self.K8S, f"fix\n\n{TRAILER}")
        self.assertEqual(decide("git push origin fix-branch", d), "deny")

    def test_push_of_clean_commit_is_silent(self):
        d = repo(self.tmp, self.K8S, "fix\n\nSigned-off-by: Dev <dev@example.com>")
        self.assertIsNone(decide("git push origin fix-branch", d))


if __name__ == "__main__":
    unittest.main()
