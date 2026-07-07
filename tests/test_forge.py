import unittest
from unittest import mock

from nemovcs import forge
from nemovcs.forge import github
from nemovcs.forge.base import ForgeContext, ForgeMatch, parse_remote_host
from nemovcs.forge.github import (
    GitHubForge,
    classify_github_host,
    gh_hosts_config_path,
    parse_gh_accounts,
    parse_gh_hosts_config,
)


class ParseRemoteHostTest(unittest.TestCase):
    def test_parses_all_common_remote_forms(self):
        cases = {
            "https://github.com/owner/repo.git": "github.com",
            "https://user@github.com/owner/repo.git": "github.com",
            "ssh://git@github.com/owner/repo.git": "github.com",
            "ssh://git@github.com:22/owner/repo.git": "github.com",
            "git@github.com:owner/repo.git": "github.com",
            "git@github.com:owner/repo": "github.com",
            "git@GitHub.com:owner/repo.git": "github.com",
            "https://gitlab.example.com:8443/group/repo.git": "gitlab.example.com",
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(parse_remote_host(remote), expected)

    def test_returns_none_for_unparseable_or_empty(self):
        self.assertIsNone(parse_remote_host(""))
        self.assertIsNone(parse_remote_host("   "))
        self.assertIsNone(parse_remote_host("/local/path/repo"))
        self.assertIsNone(parse_remote_host("file:///srv/git/repo.git"))


class ParseGhHostsConfigTest(unittest.TestCase):
    def test_reads_top_level_hosts(self):
        text = (
            "github.com:\n"
            "    users:\n"
            "        gdisirio:\n"
            "            oauth_token: xxx\n"
            "    git_protocol: ssh\n"
            "github.enterprise.example:\n"
            "    users:\n"
            "        gdisirio:\n"
        )
        self.assertEqual(
            parse_gh_hosts_config(text),
            ["github.com", "github.enterprise.example"],
        )

    def test_empty_config_returns_no_hosts(self):
        self.assertEqual(parse_gh_hosts_config(""), [])
        self.assertEqual(parse_gh_hosts_config("# just a comment\n"), [])


class ParseGhAccountsTest(unittest.TestCase):
    def test_reads_multiple_accounts_and_marks_active(self):
        text = (
            "github.com:\n"
            "    users:\n"
            "        gdisirio:\n"
            "            git_protocol: ssh\n"
            "            oauth_token: gho_aaa\n"
            "        chibios-sheriff:\n"
            "            oauth_token: gho_bbb\n"
            "    git_protocol: ssh\n"
            "    user: gdisirio\n"
            "    oauth_token: gho_aaa\n"
        )
        accounts = parse_gh_accounts(text)
        self.assertEqual(
            [(a.name, a.active) for a in accounts],
            [("gdisirio", True), ("chibios-sheriff", False)],
        )

    def test_single_account_config(self):
        text = "github.com:\n    user: solo\n    oauth_token: gho_x\n"
        accounts = parse_gh_accounts(text)
        self.assertEqual([(a.name, a.active) for a in accounts], [("solo", True)])

    def test_other_host_yields_nothing(self):
        text = "gitlab.com:\n    user: someone\n"
        self.assertEqual(parse_gh_accounts(text), [])


class ClassifyGithubHostTest(unittest.TestCase):
    def test_public_host_is_strong(self):
        self.assertEqual(
            classify_github_host("github.com", []), ForgeMatch.STRONG
        )

    def test_authenticated_enterprise_host_is_strong(self):
        self.assertEqual(
            classify_github_host(
                "github.corp.example", ["github.corp.example"]
            ),
            ForgeMatch.STRONG,
        )

    def test_github_prefixed_host_is_weak(self):
        self.assertEqual(
            classify_github_host("github.corp.example", []),
            ForgeMatch.WEAK,
        )

    def test_other_hosts_and_none_do_not_match(self):
        self.assertEqual(classify_github_host("gitlab.com", []), ForgeMatch.NONE)
        self.assertEqual(classify_github_host(None, []), ForgeMatch.NONE)


class GhHostsConfigPathTest(unittest.TestCase):
    def test_prefers_gh_config_dir(self):
        with mock.patch.dict("os.environ", {"GH_CONFIG_DIR": "/custom/gh"}, clear=False):
            self.assertEqual(str(gh_hosts_config_path()), "/custom/gh/hosts.yml")

    def test_falls_back_to_xdg_config_home(self):
        env = {"XDG_CONFIG_HOME": "/home/u/.cfg"}
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(
                str(gh_hosts_config_path()), "/home/u/.cfg/gh/hosts.yml"
            )


class GitHubForgeTest(unittest.TestCase):
    def test_match_remote_strong_for_public_host(self):
        gh = GitHubForge()
        with mock.patch.object(gh, "authenticated_hosts", return_value=[]):
            self.assertEqual(
                gh.match_remote("git@github.com:owner/repo.git"),
                ForgeMatch.STRONG,
            )

    def test_match_remote_strong_for_authenticated_enterprise_host(self):
        gh = GitHubForge()
        with mock.patch.object(
            gh, "authenticated_hosts", return_value=["github.corp.example"]
        ):
            self.assertEqual(
                gh.match_remote("https://github.corp.example/owner/repo.git"),
                ForgeMatch.STRONG,
            )

    def test_match_remote_weak_for_unauthenticated_github_prefix(self):
        gh = GitHubForge()
        with mock.patch.object(gh, "authenticated_hosts", return_value=[]):
            self.assertEqual(
                gh.match_remote("https://github.corp.example/owner/repo.git"),
                ForgeMatch.WEAK,
            )

    def test_match_remote_none_for_other_forge(self):
        gh = GitHubForge()
        with mock.patch.object(gh, "authenticated_hosts", return_value=[]):
            self.assertEqual(
                gh.match_remote("git@gitlab.com:group/repo.git"),
                ForgeMatch.NONE,
            )

    def test_actions_advertise_open_and_pull_request_verbs(self):
        actions = GitHubForge().actions(ForgeContext(root="/tmp/repo"))
        by_id = {a.id: a for a in actions}
        self.assertEqual(list(by_id), ["open", "cr-list", "cr-create"])

        self.assertEqual(by_id["open"].label, "Open on GitHub")
        self.assertEqual(by_id["open"].kind, "launch")
        self.assertEqual(by_id["open"].icon, "web-browser")

        self.assertEqual(by_id["cr-list"].label, "List Pull Requests")
        self.assertEqual(by_id["cr-list"].kind, "output")

        self.assertEqual(by_id["cr-create"].label, "Create Pull Request...")
        self.assertEqual(by_id["cr-create"].kind, "dialog")
        self.assertTrue(by_id["cr-create"].enabled)

    def test_create_action_disabled_on_default_branch(self):
        actions = GitHubForge().actions(
            ForgeContext(root="/tmp/repo", branch="main", default_branch="main")
        )
        create = next(a for a in actions if a.id == "cr-create")
        self.assertFalse(create.enabled)
        self.assertIn("feature branch", create.disabled_reason)

    def test_create_action_enabled_on_feature_branch(self):
        actions = GitHubForge().actions(
            ForgeContext(root="/tmp/repo", branch="feature", default_branch="main")
        )
        create = next(a for a in actions if a.id == "cr-create")
        self.assertTrue(create.enabled)

    def test_run_returns_command_for_known_action_only(self):
        gh = GitHubForge()
        self.assertEqual(gh.run("open", "/tmp/repo"), ["gh", "browse"])
        self.assertEqual(gh.run("cr-list", "/tmp/repo"), ["gh", "pr", "list"])
        self.assertEqual(gh.run("unknown", "/tmp/repo"), [])

    def test_change_request_create_command(self):
        gh = GitHubForge()
        self.assertEqual(
            gh.change_request_create_command(
                "/tmp/repo", title="Fix", body="Details", base="main"
            ),
            ["gh", "pr", "create", "--title", "Fix", "--body", "Details",
             "--base", "main"],
        )
        self.assertEqual(
            gh.change_request_create_command(
                "/tmp/repo", title="Fix", body="", base=None
            ),
            ["gh", "pr", "create", "--title", "Fix", "--body", ""],
        )

    def test_publish_command_uses_source_push_and_visibility(self):
        gh = GitHubForge()
        self.assertEqual(
            gh.publish_command("/tmp/repo", "myrepo", True),
            [
                "gh", "repo", "create", "myrepo",
                "--source", "/tmp/repo", "--push", "--private",
            ],
        )
        self.assertEqual(
            gh.publish_command("/tmp/repo", "myrepo", False)[-1],
            "--public",
        )

    def test_switch_account_command(self):
        self.assertEqual(
            GitHubForge().switch_account_command("gdisirio"),
            ["gh", "auth", "switch", "--hostname", "github.com", "--user", "gdisirio"],
        )

    def test_is_available_follows_cli_presence(self):
        gh = GitHubForge()
        with mock.patch("nemovcs.forge.github.shutil.which", return_value="/usr/bin/gh"):
            self.assertTrue(gh.is_available())
        with mock.patch("nemovcs.forge.github.shutil.which", return_value=None):
            self.assertFalse(gh.is_available())


class DetectForgeTest(unittest.TestCase):
    def test_detects_github_remote(self):
        with mock.patch.object(github.GitHubForge, "authenticated_hosts", return_value=[]):
            detected = forge.detect_forge("git@github.com:owner/repo.git")
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertEqual(detected.id, "github")

    def test_returns_none_for_unrecognized_remote(self):
        with mock.patch.object(github.GitHubForge, "authenticated_hosts", return_value=[]):
            self.assertIsNone(forge.detect_forge("git@gitlab.com:group/repo.git"))
            self.assertIsNone(forge.detect_forge(""))

    def test_forge_by_id(self):
        self.assertIsNotNone(forge.forge_by_id("github"))
        self.assertIsNone(forge.forge_by_id("nope"))


if __name__ == "__main__":
    unittest.main()
