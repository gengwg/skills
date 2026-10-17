#!/usr/bin/env python3
"""Tests for mcp_classify.py. Run: python3 hooks/test_mcp_classify.py"""
import json, os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_classify import classify

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_classify.py")


class Classify(unittest.TestCase):
    def check(self, cases):
        for name, want in cases:
            with self.subTest(name=name):
                self.assertEqual(classify(name)[0], want)

    def test_drafts_are_inside(self):
        self.check([
            ("mcp__plugin_operations_slack__slack_send_message_draft", "inside"),
            ("mcp__claude_ai_Gmail__create_draft", "inside"),
        ])

    def test_sends_and_deletes_are_irrecoverable(self):
        self.check([
            ("mcp__plugin_operations_slack__slack_send_message", "irrecoverable"),
            ("mcp__plugin_operations_slack__slack_schedule_message", "irrecoverable"),
            ("mcp__claude_ai_Gmail__forward", "irrecoverable"),
            ("mcp__claude_ai_Google_Drive__share_file", "irrecoverable"),
            ("mcp__Neon__delete_project", "irrecoverable"),
        ])

    def test_writes_are_irrecoverable(self):
        self.check([
            ("mcp__claude_ai_grafana-cloud__alerting_silences_write", "irrecoverable"),
            ("mcp__claude_ai_grafana-cloud__update_dashboard", "irrecoverable"),
            ("mcp__claude_ai_Notion__notion-create-pages", "irrecoverable"),
        ])

    def test_reads_are_inside(self):
        self.check([
            ("mcp__plugin_operations_slack__slack_read_channel", "inside"),
            ("mcp__claude_ai_grafana-cloud__query_prometheus", "inside"),
            ("mcp__claude_ai_grafana-cloud__get_dashboard_by_uid", "inside"),
            ("mcp__claude_ai_Notion__notion-search", "inside"),
        ])

    def test_write_verb_beats_read_verb(self):
        self.check([("mcp__x__list_and_delete_things", "irrecoverable")])

    def test_multiplexers_and_unknown_verbs(self):
        self.check([
            ("mcp__claude_ai_grafana-cloud__grafana_api_request", "multiplexer"),
            ("mcp__claude_ai_WorkOS__mutate", "multiplexer"),
            ("mcp__claude_ai_Claude_Docs__batch", "multiplexer"),
            ("mcp__Neon__run_sql", "unknown"),
            ("mcp__claude-in-chrome__navigate", "unknown"),
        ])


class Hook(unittest.TestCase):
    def run_hook(self, payload, home):
        return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                              text=True, timeout=15, env={**os.environ, "HOME": home})

    def test_logs_mcp_call_without_input_and_stays_silent(self):
        with tempfile.TemporaryDirectory() as home:
            p = self.run_hook(json.dumps({
                "session_id": "s1", "tool_name": "mcp__plugin_operations_slack__slack_send_message",
                "tool_input": {"channel_id": "C1", "message": "secret text"}}), home)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
            log = open(os.path.join(home, ".claude", "mcp-classify.jsonl")).read()
            row = json.loads(log)
            self.assertEqual((row["session"], row["class"], row["why"]), ("s1", "irrecoverable", "send"))
            self.assertNotIn("secret text", log)

    def test_ignores_non_mcp_tools(self):
        with tempfile.TemporaryDirectory() as home:
            self.run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}), home)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude", "mcp-classify.jsonl")))

    def test_bad_input_never_fails_the_call(self):
        with tempfile.TemporaryDirectory() as home:
            p = self.run_hook("not json", home)
            self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
