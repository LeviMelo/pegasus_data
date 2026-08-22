"""Where the data goes: five layers, and the reason each path won.

Placement was overridable before, but only in ways you had to remember every
time, and only as one directory. These tests pin the three things that changed:
resolution no longer follows the working directory blindly, it can be written
down, and the cache can live somewhere other than the lake.
"""

from __future__ import annotations

import pytest

from pegasus_data.config import Settings, load_settings
from pegasus_data.locate import (
    PLACEMENT_KEYS,
    config_search_path,
    find_project_config,
    read_config_file,
    resolve_placement,
    user_config_path,
    write_config_file,
)


def _home(root, *, catalog=True):
    """A directory that looks like a data home that has been used."""
    (root / ("_catalog" if catalog else "blobs")).mkdir(parents=True)
    return root


class TestItNoLongerFollowsTheWorkingDirectory:
    """The oldest surprise: `cd` into a subdirectory, and the catalog looks wiped."""

    def test_a_command_run_from_a_subdirectory_finds_the_same_home(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        _home(project / "pegasus_data_home")
        deep = project / "src" / "analysis" / "deep"
        deep.mkdir(parents=True)

        monkeypatch.chdir(deep)
        assert resolve_placement()["root"].value == (project / "pegasus_data_home").resolve()

    def test_an_empty_directory_of_the_right_name_is_not_adopted(self, tmp_path, monkeypatch):
        """Otherwise a bare `pegasus_data_home` anywhere above you hijacks the
        command; only a home that already holds something counts as evidence."""
        (tmp_path / "pegasus_data_home").mkdir()
        here = tmp_path / "work"
        here.mkdir()
        monkeypatch.chdir(here)
        assert resolve_placement()["root"].value == (here / "pegasus_data_home").resolve()

    def test_a_blob_store_counts_as_evidence_too(self, tmp_path, monkeypatch):
        _home(tmp_path / "pegasus_data_home", catalog=False)
        here = tmp_path / "work"
        here.mkdir()
        monkeypatch.chdir(here)
        assert resolve_placement()["root"].value == (tmp_path / "pegasus_data_home").resolve()

    def test_with_nothing_anywhere_it_still_lands_beside_you(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        decided = resolve_placement()["root"]
        assert decided.value == (tmp_path / "pegasus_data_home").resolve()
        assert decided.source == "default"


class TestPrecedence:
    """Five layers. The one that wins must be the one the reader expects."""

    @pytest.fixture
    def layered(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        write_config_file(project / "pegasus-data.toml", {"root": str(tmp_path / "from-project")})
        user = tmp_path / "user.toml"
        write_config_file(user, {"root": str(tmp_path / "from-user")})
        monkeypatch.setenv("PEGASUS_CONFIG", str(user))
        monkeypatch.chdir(project)
        return tmp_path

    def test_an_explicit_argument_beats_everything(self, layered, monkeypatch):
        monkeypatch.setenv("PEGASUS_DATA_HOME", str(layered / "from-env"))
        got = resolve_placement({"root": layered / "from-argument"})["root"]
        assert got.value == layered / "from-argument"
        assert got.source == "argument"

    def test_the_environment_beats_both_files(self, layered, monkeypatch):
        monkeypatch.setenv("PEGASUS_DATA_HOME", str(layered / "from-env"))
        got = resolve_placement()["root"]
        assert got.value == layered / "from-env"
        assert got.source == "environment"

    def test_the_project_file_beats_the_user_file(self, layered):
        got = resolve_placement()["root"]
        assert got.value == layered / "from-project"
        assert "project" in got.origin

    def test_the_user_file_beats_the_default(self, tmp_path, monkeypatch):
        user = tmp_path / "user.toml"
        write_config_file(user, {"root": str(tmp_path / "from-user")})
        monkeypatch.setenv("PEGASUS_CONFIG", str(user))
        here = tmp_path / "elsewhere"
        here.mkdir()
        monkeypatch.chdir(here)
        got = resolve_placement()["root"]
        assert got.value == tmp_path / "from-user"
        assert "user" in got.origin

    def test_every_resolved_path_says_who_decided_it(self, layered):
        for key, decided in resolve_placement().items():
            assert decided.source, key
            assert decided.describe(), key


class TestTheCacheCanLiveElsewhere:
    """A blob cache is large, rebuildable and write-heavy; the lake is what you
    query. Forcing them onto one volume was a real constraint."""

    def test_blobs_lake_catalog_and_work_are_independently_placeable(self, tmp_path):
        settings = Settings(
            root=tmp_path / "root",
            blobs_root=tmp_path / "big" / "blobs",
            lake_root=tmp_path / "fast" / "lake",
            work_root=tmp_path / "scratch",
            catalog_root=tmp_path / "fast" / "cat",
        )
        assert settings.blobs_dir == tmp_path / "big" / "blobs"
        assert settings.lake_dir == tmp_path / "fast" / "lake"
        assert settings.work_dir == tmp_path / "scratch"
        assert settings.catalog_path == tmp_path / "fast" / "cat" / "catalog.sqlite"

    def test_unset_keys_still_derive_from_root(self, tmp_path):
        settings = Settings(root=tmp_path / "r", blobs_root=tmp_path / "elsewhere")
        assert settings.blobs_dir == tmp_path / "elsewhere"
        assert settings.lake_dir == tmp_path / "r" / "lake"
        assert settings.catalog_path == tmp_path / "r" / "_catalog" / "catalog.sqlite"

    def test_ensure_dirs_creates_the_overridden_places_not_the_derived_ones(self, tmp_path):
        settings = Settings(root=tmp_path / "r", blobs_root=tmp_path / "big" / "blobs")
        settings.ensure_dirs()
        assert (tmp_path / "big" / "blobs").is_dir()
        assert not (tmp_path / "r" / "blobs").exists(), (
            "the derived location must not be created when it is not in use"
        )

    def test_places_reports_every_directory_written_to(self, tmp_path):
        places = Settings(root=tmp_path).places()
        assert set(places) == set(PLACEMENT_KEYS)

    def test_load_settings_applies_a_split_from_a_config_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config_file(
            tmp_path / "pegasus-data.toml",
            {"root": str(tmp_path / "data"), "blobs": str(tmp_path / "big")},
        )
        settings = load_settings()
        assert settings.blobs_dir == tmp_path / "big"
        assert settings.lake_dir == tmp_path / "data" / "lake"
        assert settings.origins["blobs"].startswith("config file")


class TestConfigFiles:
    def test_a_file_round_trips(self, tmp_path):
        target = tmp_path / "pegasus-data.toml"
        write_config_file(target, {"root": "/data", "blobs": "/big"})
        assert read_config_file(target) == {"root": "/data", "blobs": "/big"}

    def test_writing_preserves_what_it_did_not_write(self, tmp_path):
        """A config file is usually not only ours."""
        target = tmp_path / "pegasus-data.toml"
        target.write_text('[other-tool]\nsetting = "keep me"\n', encoding="utf-8")
        write_config_file(target, {"root": "/data"})
        text = target.read_text(encoding="utf-8")
        assert "other-tool" in text and "keep me" in text
        assert read_config_file(target) == {"root": "/data"}

    def test_windows_paths_survive_the_round_trip(self, tmp_path):
        """Backslashes are TOML escapes; an unescaped one silently corrupts."""
        target = tmp_path / "pegasus-data.toml"
        write_config_file(target, {"root": r"C:\Users\me\datasus"})
        assert read_config_file(target)["root"] == r"C:\Users\me\datasus"

    def test_a_tool_table_is_read_too(self, tmp_path):
        """So the settings can live in a file the project already has."""
        target = tmp_path / "pegasus-data.toml"
        target.write_text('[tool.pegasus-data]\nroot = "/data"\n', encoding="utf-8")
        assert read_config_file(target) == {"root": "/data"}

    def test_a_malformed_file_is_an_error_not_a_shrug(self, tmp_path):
        """Silently ignoring a file written on purpose is how 'my setting does
        nothing' happens."""
        target = tmp_path / "pegasus-data.toml"
        target.write_text("this is not = = toml", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid TOML"):
            read_config_file(target)

    def test_a_file_without_our_table_contributes_nothing(self, tmp_path):
        target = tmp_path / "pegasus-data.toml"
        target.write_text('[something-else]\nx = 1\n', encoding="utf-8")
        assert read_config_file(target) == {}

    def test_an_absent_file_is_not_an_error(self, tmp_path):
        assert read_config_file(tmp_path / "nope.toml") == {}

    def test_the_dotted_name_is_read(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pegasus-data.toml").write_text(
            '[pegasus-data]\nroot = "/hidden"\n', encoding="utf-8"
        )
        assert find_project_config() == tmp_path / ".pegasus-data.toml"

    def test_the_search_path_lists_absent_files_too(self, tmp_path, monkeypatch):
        """'I edited the config and nothing changed' is almost always a file in
        a place nothing reads."""
        monkeypatch.chdir(tmp_path)
        scopes = {scope for scope, _p, _e in config_search_path()}
        assert scopes == {"project", "user"}

    def test_the_user_path_is_overridable_for_testing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PEGASUS_CONFIG", str(tmp_path / "custom.toml"))
        assert user_config_path() == tmp_path / "custom.toml"


class TestOtherSettingsFromFiles:
    def test_a_file_can_set_throughput_too(self, tmp_path, monkeypatch):
        """A file that can say where the data goes but not how hard to push the
        server would be an arbitrary line to draw."""
        monkeypatch.chdir(tmp_path)
        write_config_file(tmp_path / "pegasus-data.toml", {"connections": 2, "host": "example.test"})
        settings = load_settings()
        assert settings.connections == 2
        assert settings.host == "example.test"

    def test_the_environment_still_beats_the_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config_file(tmp_path / "pegasus-data.toml", {"connections": 2})
        monkeypatch.setenv("PEGASUS_CONNECTIONS", "7")
        assert load_settings().connections == 7

    def test_an_explicit_argument_still_beats_both(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config_file(tmp_path / "pegasus-data.toml", {"connections": 2})
        monkeypatch.setenv("PEGASUS_CONNECTIONS", "7")
        assert load_settings(connections=3).connections == 3

    def test_an_unknown_key_is_ignored_rather_than_crashing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config_file(tmp_path / "pegasus-data.toml", {"not_a_setting": "x"})
        load_settings()
