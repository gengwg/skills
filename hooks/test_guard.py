#!/usr/bin/env python3
"""Tests for guard.py. Run: python3 hooks/test_guard.py"""
import json, os, shutil, subprocess, sys, tempfile, unittest, unittest.mock

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py")


def decide(command, cwd="/home/user/proj", home="/home/user"):
    """Run the hook and return its permissionDecision, or None if it stayed silent."""
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, timeout=15, env={**os.environ, "HOME": home})
    if not p.stdout.strip():
        return None
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


class MergeGuard(unittest.TestCase):
    def test_gitlab_mr_merge_asks(self):
        self.assertEqual(decide("glab mr merge 12 --yes"), "ask")

    def test_github_pr_merge_is_silent(self):
        self.assertIsNone(decide("gh pr merge 41 --squash --delete-branch"))


class RmGuard(unittest.TestCase):
    def test_rf_outside_scratch_asks(self):
        self.assertEqual(decide("rm -rf /home/user/proj/build"), "ask")

    def test_rf_in_scratch_is_silent(self):
        self.assertIsNone(decide("rm -rf /tmp/claude/sess/tmpdir"))

    def test_rf_in_worktree_is_silent(self):
        self.assertIsNone(decide("rm -rf /home/user/worktrees/feat"))

    def test_rf_inside_any_project_tmp_is_silent(self):
        self.assertIsNone(decide("rm -rf tmp/*"))
        self.assertIsNone(decide("rm -rf tmp/build /home/user/proj/tmp/x"))
        self.assertIsNone(decide("rm -rf /home/user/other/tmp/x"))

    def test_rf_tmp_itself_escape_or_system_tmp_asks(self):
        self.assertEqual(decide("rm -rf tmp"), "ask")
        self.assertEqual(decide("rm -rf /home/user/other/tmp"), "ask")
        self.assertEqual(decide("rm -rf tmp/../src"), "ask")
        self.assertEqual(decide("rm -rf /tmp/build"), "ask")
        self.assertEqual(decide("rm -rf //tmp/build"), "ask")
        self.assertEqual(decide("rm -rf /var/tmp/build"), "ask")
        self.assertEqual(decide("rm -rf /etc/x/tmp/y"), "ask")

    def test_rf_home_from_a_tmp_cwd_asks(self):
        self.assertEqual(decide("rm -rf ~", cwd="/home/user/proj/tmp/a"), "ask")
        self.assertEqual(decide("rm -rf ~/.ssh", cwd="/home/user/proj/tmp/a"), "ask")

    def test_rf_shell_rewritten_paths_ask(self):
        tmp_cwd = "/home/user/proj/tmp/a"
        for cmd, cwd in [
            ("rm -rf {~,a/tmp/b}", "/home/user/proj"),
            ("rm -rf {/home,a/tmp/b}", "/home/user/proj"),
            ("rm -rf tmp/{x,../../..}", "/home/user/proj"),
            ("rm -rf ~/p/tmp/q/`:`/../../..", "/home/user/proj"),
            ("(rm -rf ~)", tmp_cwd),
            ("echo `rm -rf ~`", tmp_cwd),
            ("rm -rf ~>/dev/null", tmp_cwd),
            ("rm -rf ~-", tmp_cwd),
            ("rm -rf ~+/..", tmp_cwd),
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(decide(cmd, cwd=cwd), "ask")

    def test_rf_tmp_allow_needs_plain_tokens_and_real_path(self):
        # /var/tmp, not $TMPDIR: a scratchpad or worktrees TMPDIR would hit the
        # other allow branches and mask the asks below.
        home = tempfile.mkdtemp(dir="/var/tmp")
        try:
            proj = os.path.join(home, "proj")
            os.makedirs(os.path.join(proj, "tmp"))
            # tmp/link points back at $HOME: the literal path has a tmp segment,
            # the real path does not.
            os.symlink(home, os.path.join(proj, "tmp", "link"))
            dec = lambda cmd, cwd=proj: decide(cmd, cwd=cwd, home=home)
            self.assertIsNone(dec("rm -rf tmp/build"))
            self.assertIsNone(dec("rm -rf tmp/*"))
            self.assertIsNone(dec("rm -rf *", cwd=os.path.join(proj, "tmp")))
            self.assertIsNone(dec("rm -rf ~/proj/tmp/x"))
            self.assertEqual(dec("rm -rf *"), "ask")
            self.assertEqual(dec("rm -rf tmp/link"), "ask")
            self.assertEqual(dec("rm -rf tmp/link/x"), "ask")
            self.assertEqual(dec("rm -rf tmp/[ab]"), "ask")
            self.assertEqual(dec("rm -rf tmp/a*/../.."), "ask")
        finally:
            shutil.rmtree(home)

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
    run = lambda *a: subprocess.run(["git", "-C", tmp, "-c", "commit.gpgsign=false", "-c", "user.name=t",
                                     "-c", "user.email=t@example.com", *a],
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

    def test_push_from_fork_only_clone_denied(self):
        # Real forks get deleted; a stub gh answers the parent lookup without network or auth.
        bindir = os.path.join(self.tmp, "bin")
        os.mkdir(bindir)
        with open(os.path.join(bindir, "gh"), "w") as f:
            f.write("#!/bin/sh\necho kubernetes-sigs/kubespray\n")
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        d = repo(self.tmp, "https://github.com/someone/kubespray.git", f"fix\n\n{TRAILER}")
        with unittest.mock.patch.dict(os.environ, {"PATH": bindir + os.pathsep + os.environ["PATH"]}):
            self.assertEqual(decide("git push origin fix-branch", d), "deny")

    def test_push_of_clean_commit_is_silent(self):
        d = repo(self.tmp, self.K8S, "fix\n\nSigned-off-by: Dev <dev@example.com>")
        self.assertIsNone(decide("git push origin fix-branch", d))


if __name__ == "__main__":
    unittest.main()
