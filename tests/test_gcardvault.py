import os
import glob
import re
import json
from pathlib import Path
import shutil
import pytest
from unittest.mock import MagicMock, patch
from git import Repo
from gcardvault import Gcardvault, GcardvaultError
from gcardvault.gcardvault import GoogleOAuth2

from .fake_google_apis import FakeDataRepo, FakeGoogleApis


# Note: Tests are meant to run in a container (see `make test`), so
# tests here are written against the actual file system, including
# git functionalities. All HTTP requests out to Google APIs are
# mocked, however.


dirname = os.path.dirname(__file__)
data_dir_path = os.path.join(dirname, "data")
fake_data_repo = FakeDataRepo()


@pytest.mark.parametrize(
    "args", [
        ["--unknown"],  # bad long option
        ["-u"],  # bad short option
        ["badcommand", "foo.bar@gmail.com"],  # bad command
        ["--export-only"],  # valid option with no command
        ["noop"],  # valid command with no user
    ])
def test_invalid_args(args):
    gc = Gcardvault()
    with pytest.raises(GcardvaultError):
        gc.run(args)


@pytest.mark.parametrize(
    "args", [
        ["--help"],
        ["-h"],
        [],
    ])
def test_help(capsys, args):
    gc = Gcardvault()
    gc.run(args)

    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "Options:" in captured.out


@pytest.mark.parametrize(
    "args", [
        ["--version"],
    ])
def test_version(capsys, args):
    gc = Gcardvault()
    gc.run(args)

    # Success if output casts to a float w/o throwing exception
    captured = capsys.readouterr()
    assert re.match(r"^\d+\.\d+(\.\d+)?$", captured.out.strip())


@pytest.mark.parametrize(
    "args, expected_properties", [
        (["noop", "foo.bar@gmail.com"],
            {'command': "noop", 'user': "foo.bar@gmail.com"}),
        (["noop", "foo.bar@gmail.com", "-e"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "--export-only"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "-f"],
            {'clean': True}),
        (["noop", "foo.bar@gmail.com", "--clean"],
            {'clean': True}),
        (["noop", "foo.bar@gmail.com", "-c", "/tmp/conf"],
            {'conf_dir': "/tmp/conf"}),
        (["noop", "foo.bar@gmail.com", "--conf-dir", "/tmp/conf"],
            {'conf_dir': "/tmp/conf"}),
        (["noop", "foo.bar@gmail.com", "-o", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--output-dir", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--vault-dir", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--client-id", "0123456789abcdef"],
            {'client_id': "0123456789abcdef"}),
        (["noop", "foo.bar@gmail.com", "--client-secret", "!@#$%^&*"],
            {'client_secret': "!@#$%^&*"}),
    ])
def test_arg_parsing(args, expected_properties):
    gc = Gcardvault()
    gc.run(args)

    for key, expected_value in expected_properties.items():
        actual_value = getattr(gc, key)
        assert actual_value == expected_value


def test_creates_dirs():
    (conf_dir, output_dir) = _setup_dirs()
    gc = Gcardvault()
    gc.run(["noop", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert conf_dir.is_dir() and conf_dir.exists()
    assert output_dir.is_dir() and output_dir.exists()


def test_sync():
    (conf_dir, output_dir) = _setup_dirs()
    google_apis_fake = FakeGoogleApis(fake_data_repo)

    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    _assert_vcf_files_match(output_dir, google_apis_fake.count, google_apis_fake.records)


def test_clean():
    (conf_dir, output_dir) = _setup_dirs()

    # With more results
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=5)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)
    _assert_git_repo_state(output_dir, commit_count=2, last_commit_file_count=5)  # initial commit + 1, 5 vcf files

    # With fewer results
    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "--clean", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_2.count, google_apis_fake_2.records)
    _assert_git_repo_state(output_dir, commit_count=3, last_commit_file_count=2)  # 1 additional commit, 2 file removals


def test_without_clean():
    (conf_dir, output_dir) = _setup_dirs()

    # With more results
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=5)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)
    _assert_git_repo_state(output_dir, commit_count=2, last_commit_file_count=5)  # initial commit + 1, 5 vcf files

    # With fewer results, but no --clean, should have all VCF files
    # from first run
    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)
    _assert_git_repo_state(output_dir, commit_count=2)  # additional commit


def test_sync_export_only():
    (conf_dir, output_dir) = _setup_dirs()
    google_apis_fake = FakeGoogleApis(fake_data_repo, cap=3)

    # --export-only
    # Shouldn't create git repo, but should write files to disk
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake)
    gc.run(["sync", "foo.bar@gmail.com", "--export-only", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, repo_exists=False)
    _assert_vcf_files_match(output_dir, google_apis_fake.count)


def test_new_git_repo():
    (conf_dir, output_dir) = _setup_dirs()
    google_apis_fake = FakeGoogleApis(fake_data_repo, cap=0)

    # No files to commit, but git repo should be created with
    # one commit (the .gitignore)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, commit_count=1)  # initial commit


def test_git_commits():
    (conf_dir, output_dir) = _setup_dirs()
    google_apis_fake = FakeGoogleApis(fake_data_repo, cap=3)

    # Git repo should have two commits, initial commit plus
    # files downloaded
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, commit_count=2, last_commit_file_count=3)  # initial commit + 1, 3 vcf files


def test_etags_none_changed():
    (conf_dir, output_dir) = _setup_dirs()

    # Initial request, will fetch all records and record etags
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)

    # Second request, no etag changes so no vcard updates be requested
    # vcards_allowlist is empty
    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3, vcards_allowlist=[])
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)


def test_etags_none_changed_but_files_missing():
    (conf_dir, output_dir) = _setup_dirs()

    # Initial request, will fetch all records and record etags
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)

    record_to_get = google_apis_fake_1.records[1]
    os.remove(os.path.join(output_dir, record_to_get["file_name"]))

    # Second request, no etag changes but one file is missing
    # so it should be requested and file should be restored
    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3, vcards_allowlist=[record_to_get["href"]])
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)


def test_etags_some_changed():
    (conf_dir, output_dir) = _setup_dirs()

    # Initial request
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)

    # Same number of records, but with one etag changed

    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3, vcards_allowlist=[])
    record = google_apis_fake_2.touch_record(1)
    google_apis_fake_2.allow_vcards([record["href"]])

    assert google_apis_fake_2.records[1]["etag"] != google_apis_fake_1.records[1]["etag"]

    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_2.count, google_apis_fake_2.records)


def test_etags_some_added():
    (conf_dir, output_dir) = _setup_dirs()

    # Initial request
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)

    # More records on the second request
    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=6, vcards_allowlist=[])
    google_apis_fake_2.allow_vcards(record["href"] for record in google_apis_fake_2.records[3:6])
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_2.count, google_apis_fake_2.records)


def test_sync_name_change():
    (conf_dir, output_dir) = _setup_dirs()

    # Initial request
    google_apis_fake_1 = FakeGoogleApis(fake_data_repo, cap=3)
    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_1)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    _assert_vcf_files_match(output_dir, google_apis_fake_1.count, google_apis_fake_1.records)

    # Same records, name changes, file name should change too

    google_apis_fake_2 = FakeGoogleApis(fake_data_repo, cap=3, vcards_allowlist=[])

    old_file_name = google_apis_fake_2.records[1]["file_name"]
    record = google_apis_fake_2.change_name(1, "Foo", "Bar")
    new_file_name = record["file_name"]

    google_apis_fake_2.allow_vcards([record["href"]])

    gc = Gcardvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=google_apis_fake_2)
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert not os.path.exists(os.path.join(output_dir, old_file_name))
    assert os.path.exists(os.path.join(output_dir, new_file_name))
    _assert_vcf_files_match(output_dir, google_apis_fake_2.count, google_apis_fake_2.records)


def _assert_vcf_files_match(output_dir, count, records_to_validate=[]):
    actual_files = [os.path.basename(f) for f in glob.glob(os.path.join(output_dir, "*.vcf"))]

    assert count == len(actual_files)

    for record in records_to_validate:
        assert record["file_name"] in actual_files
        _assert_vcf_file_content_match(output_dir, record["file_name"], record["vcard"])


def _assert_vcf_file_content_match(output_dir, output_file_name, expected_content):
    assert _read_file(output_dir, output_file_name) == expected_content


def _setup_dirs():
    conf_dir = Path("/tmp/conf")
    output_dir = Path("/tmp/output")

    for dir in [conf_dir, output_dir]:
        if dir.exists():
            shutil.rmtree(dir)

    return (conf_dir.resolve(), output_dir.resolve())


def _get_google_oauth2_mock(new_authorization=False, email="foo.bar@gmail.com"):
    google_oauth2 = GoogleOAuth2("gcardvault", "gcardvault authorize")

    credentials = MagicMock(token="phony")
    google_oauth2.get_credentials = MagicMock(return_value=(credentials, new_authorization))

    user_info = {"email": email}
    google_oauth2.request_user_info = MagicMock(return_value=user_info)

    return google_oauth2


def _read_file(dir_path, file_name):
    return Path(dir_path, file_name).read_text()


def _assert_git_repo_state(output_dir, repo_exists=True, commit_count=None, last_commit_file_count=None):
    assert os.path.exists(os.path.join(output_dir, ".git")) == repo_exists
    if commit_count is not None or last_commit_file_count is not None:
        repo = Repo(output_dir)
        commits = list(repo.iter_commits(rev=repo.head.reference, max_count=10))
        if commit_count is not None:
            assert len(commits) == commit_count
        if last_commit_file_count is not None:
            assert commits[0].stats.total["files"] == last_commit_file_count
