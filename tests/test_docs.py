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


def test_link_forms_are_parsed(git_repo: Path) -> None:
    write(git_repo, "My File.md", "# Spaces\n")
    write(git_repo, "foo(1).md", "# Parentheses\n")
    write(git_repo, "docs/guide.md", "# Folder\n")
    write(
        git_repo,
        "a.md",
        "[spaces](<My File.md>) [parens](foo(1).md) [folder](docs/) [root](/docs/guide.md)\n"
        "[gone](<Gone File.md>)\n"
        "- item\n\n  ```md\n  [listed](nope.md)\n  ```\n"
        "<!-- [commented](nope.md) -->\n"
        "[ref]: missing-ref.md\n"
        "[^note]: Footnote text, not a link.\n",
    )
    assert docs.check(git_repo) == [
        "a.md: broken link to Gone File.md",
        "a.md: broken link to missing-ref.md",
    ]


def test_link_must_work_in_a_fresh_clone(git_repo: Path) -> None:
    write(git_repo, ".gitignore", "private.md\n")
    write(git_repo, "private.md", "# Ignored\n")
    write(git_repo, "b.md", "# B\n")
    write(git_repo, "a.md", "[ignored](private.md) [case](B.md) [ok](b.md)\n")
    assert docs.check(git_repo) == [
        "a.md: broken link to private.md",
        "a.md: broken link to B.md",
    ]


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


def test_invalid_frontmatter_is_named_and_other_problems_still_reported(git_repo: Path) -> None:
    write(
        git_repo, ".agents/skills/demo/SKILL.md", "---\nname: demo\ndescription: Use when: x\n---\n"
    )
    write(git_repo, "a.md", "[gone](missing.md)\n")
    problems = docs.check(git_repo)
    assert problems[0] == "a.md: broken link to missing.md"
    assert problems[1].startswith(
        ".agents/skills/demo/SKILL.md: frontmatter is not valid YAML: mapping values"
    )
    assert len(problems) == 2
