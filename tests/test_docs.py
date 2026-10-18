"""The documentation check catches broken links and skill frontmatter drift."""

from pathlib import Path

from checks import docs


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def skill(repo: Path, base: str, folder: str, name: str, description: str) -> None:
    write(
        repo, f"{base}/{folder}/SKILL.md", f"---\nname: {name}\ndescription: {description}\n---\n"
    )


def test_broken_local_link_fails(git_repo: Path) -> None:
    write(git_repo, "b.md", "# B\n")
    write(
        git_repo,
        "docs/a.md",
        "[ok](../b.md) [gone](missing.md) [web](https://example.com) [here](#top)\n"
        "`[code](nope.md)`\n```md\n[fenced](also-nope.md)\n```\n",
    )
    assert docs.check(git_repo) == ["docs/a.md: broken link to missing.md"]


def test_matching_pointer_passes(git_repo: Path) -> None:
    skill(git_repo, ".agents/skills", "demo", "demo", "Does the demo thing.")
    skill(git_repo, ".claude/skills", "demo", "demo", "Does the demo thing.")
    assert docs.check(git_repo) == []


def test_pointer_drift_fails(git_repo: Path) -> None:
    skill(git_repo, ".agents/skills", "demo", "demo", "Does the demo thing.")
    skill(git_repo, ".claude/skills", "demo", "demo", "Does something else.")
    assert docs.check(git_repo) == [
        ".claude/skills/demo/SKILL.md: description differs from its canonical .agents skill"
    ]


def test_name_folder_mismatch_fails(git_repo: Path) -> None:
    skill(git_repo, ".agents/skills", "demo", "other", "Does the demo thing.")
    assert docs.check(git_repo) == [
        ".agents/skills/demo/SKILL.md: name 'other' does not match its folder"
    ]


def test_missing_description_fails(git_repo: Path) -> None:
    write(git_repo, ".agents/skills/demo/SKILL.md", "---\nname: demo\n---\n")
    assert docs.check(git_repo) == [".agents/skills/demo/SKILL.md: no description"]
