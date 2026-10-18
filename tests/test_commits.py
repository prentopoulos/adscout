"""The commit check enforces Conventional Commits on the branch's own commits."""

from pathlib import Path

from checks import commits
from conftest import run_git


def commit(repo: Path, subject: str) -> None:
    run_git(repo, "commit", "-q", "--allow-empty", "-m", subject)


def branch(repo: Path, name: str) -> None:
    run_git(repo, "checkout", "-q", "-b", name)


def test_valid_subjects_pass(git_repo: Path) -> None:
    commit(git_repo, "chore: initial commit")
    branch(git_repo, "feature")
    commit(git_repo, "feat(cli): add the version command")
    commit(git_repo, "fix!: drop the old flag")
    assert commits.check(git_repo) == []


def test_bad_subject_fails(git_repo: Path) -> None:
    commit(git_repo, "chore: initial commit")
    branch(git_repo, "feature")
    commit(git_repo, "updated stuff")
    problems = commits.check(git_repo)
    assert len(problems) == 1
    assert problems[0].endswith(": subject 'updated stuff' is not a Conventional Commit")


def test_merge_commits_are_exempt(git_repo: Path) -> None:
    commit(git_repo, "chore: initial commit")
    branch(git_repo, "feature")
    commit(git_repo, "feat: first part")
    branch(git_repo, "side")
    commit(git_repo, "docs: side note")
    run_git(git_repo, "checkout", "-q", "feature")
    run_git(git_repo, "merge", "-q", "--no-ff", "side", "-m", "Merge branch 'side'")
    assert commits.check(git_repo) == []


def test_commits_already_on_main_are_not_checked(git_repo: Path) -> None:
    commit(git_repo, "initial import")
    branch(git_repo, "feature")
    commit(git_repo, "docs: describe the project")
    assert commits.check(git_repo) == []


def test_missing_main_fails(git_repo: Path) -> None:
    # main has no commits yet, so switching branches first means it never exists.
    branch(git_repo, "trunk")
    commit(git_repo, "chore: initial commit")
    assert commits.check(git_repo) == ["no main or origin/main branch to compare commits against"]
