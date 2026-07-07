import unittest
from unittest import mock

from nemovcs import forge
from nemovcs.forge import github
from nemovcs.forge.base import ForgeMatch, parse_remote_host
from nemovcs.forge.github import (
    GitHubForge,
    classify_github_host,
    gh_hosts_config_path,
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

    def test_open_in_browser_command(self):
        self.assertEqual(
            GitHubForge().open_in_browser_command("/tmp/repo"),
            ["gh", "browse"],
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
