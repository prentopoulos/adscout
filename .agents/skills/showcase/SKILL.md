---
name: showcase
description: How to make a project's public showcase - the slide deck, the walkthrough video, the README, the architecture diagrams and other write-ups for recruiters or contacts - in the owner's style. Use when a phase produces a deck, video, README, methodology, architecture diagram or other public-facing document, or when the owner asks for slides, a recording, diagrams or a portfolio page.
---

# Showcase: deck, video and README

These are the owner's preferences, learned while building the Compute Cost & Risk Monitor demo
(October 2026). They apply to anything someone outside the project will read or watch.
Dashboards and app screens keep their own terse style; this style is for decks, documents and
videos.

## Writing style

- **Explain to a newcomer first.** Cover what it is, who uses it, why it matters and how it
  works. Assume the reader knows nothing about the project.
- **Write lines a person would say out loud** when presenting the project in an interview. Use
  short sentences and everyday words: "data transfer", not "egress"; "the same kind of
  machine", not "like with like".
- **No slogans or reassurance taglines** in headlines, captions or cards. The owner rejected
  both "Code computes every number. AI writes only words." and "…, with every figure checked by
  code" as cringe and unprofessional. Name the feature plainly ("AI-powered market brief"), and
  leave safeguards to the body text.
- **No meta captions** that explain the slide's own visuals ("Words by Claude. Blue numbers
  filled in by code."). **No internal process notes** ("If the AI breaks a rule, its text is
  thrown away…").
- **Keep the labels the project's rules require**, such as "synthetic data", "not a forecast"
  and cost exclusions, short and in plain words. They are rules, not taglines.
- **Before showing a draft, reread every line, small print included.** Remove anything the
  owner would call internal, defensive or AI-sounding. Don't leave them to find these one by
  one.

## Deck (Figma Slides)

- Build it with `use_figma` and the figma-use-slides skill. Draft it, run the batch validation,
  screenshot it, show the owner, then fix it line by line.
- **A six-slide story that worked:**
  1. what it is, and who uses it;
  2. why it matters (the market or business context);
  3. how it works (steps and one worked example);
  4. what you see (an annotated screenshot);
  5. how it uses AI, if it does;
  6. limits and next steps.
- When a line wraps awkwardly, shorten the words before touching the font. The owner asked for
  one-line notes to stay on one line.
- **PDF without the owner:**
  - export each slide with `download_assets` (`defaultFormat: "pdf"`);
  - fetch each URL at once, since they expire;
  - merge in order with pypdf (`uv run --no-project --with pypdf python -I merge.py`);
  - check the page count and look at one page.

  After any edit, re-export only the changed slide.

## Walkthrough video

The owner may be away, and Claude can record it. See
[references/walkthrough-recording.md](references/walkthrough-recording.md) and the worked example
[references/record-walkthrough.example.mjs](references/record-walkthrough.example.mjs).

- **About two minutes**, with on-screen captions instead of a voice, using demo or synthetic
  data only.
- **Write the timed script first** (`docs/walkthrough.md`). The captions are its lines. Measure
  the real times from the finished video afterwards.
- **Run a preview pass** of one still per step, and check that every highlight lands, before
  recording.
- **Send the MP4 to the owner** (SendUserFile) before committing it anywhere. Where it is
  published is the owner's call. Once the owner says a take is fine, stop re-recording.

## README

- **Follow the owner's reference README for its shape:** github.com/prentopoulos/fundamental-engine.
  It is PolyForm-licensed, so reuse the shape, not the text.
- **Open with** the user's question and the bottom line. Then the links:
  - the deck ("Start here");
  - the video ("Watch");
  - the methodology and report ("Read").

  Then one sentence on any AI feature, one screenshot, and a single command to try it.
- **Test the figures.** Put computed figures between hidden markers
  (`<!-- bottom-line:start -->`), and test every number there against its source facts. Add a
  test that a drifted figure gets caught.
- **Test the links and licences.** Every local link must resolve to a tracked file, and the
  licence and third-party credits must be named.

## Architecture diagrams (C4)

Draw them to the C4 model's notation ([c4model.com/diagrams/notation](https://c4model.com/diagrams/notation)),
because that is what engineers expect.

**Default tool: diagrams as code.** The owner decided this on 2026-10-15.
- Keep one Structurizr DSL model in `docs/architecture/workspace.dsl`, with a context view
  and a container view (plus a component view if useful). It lives in Git and changes in
  pull requests.
- Export the views as SVG for the docs, and as Mermaid where a diagram should render directly
  in the README. GitHub renders Mermaid code blocks.
- Use Figma or FigJam for slides and visual mock-ups, not for architecture diagrams, unless the
  owner asks.

Commands, a starter model and the FigJam technique are in
[references/c4-diagrams.md](references/c4-diagrams.md).

- **Title** each diagram with its type and scope: "Container diagram for <system>".
- **Give every diagram a key** that explains its colours, shapes, line styles and arrows.
- **Every element** shows its name, its type, its technology (for containers) and a one-line
  description of what it does.
- **Every line** goes one way and carries a specific verb label ("Reads list prices", never
  "Uses"), plus its technology or protocol, e.g. "[HTTPS, JSON]" or "[SQL]".
- **A container is something that runs or stores data:** an app, a command-line tool, a
  database or a file store. Modules and libraries belong in the description of the container
  that holds them, or in a component diagram.
- **Colours are free, but must mean the same thing in every view.** For example, blue for the
  system and its containers, and white for people and external systems.
- **Keep it readable:** about 15–20 elements at most. Labels must not overlap or sit on another
  line.
- **Space it evenly.** Use equal gaps between columns and equal margins on both sides, space
  rows evenly, and centre a box between the boxes it connects. Check this by measuring the
  gaps, not by eye.

## Before anything goes public

The full method, including how to prove the secret scanner works, is in
[references/pre-publication.md](references/pre-publication.md).

Making the repository public is the owner's gate. Before or right after it:
- scan every blob in the history for secrets, and prove the scanner works with a planted test
  key;
- survey the history for data that must not be published;
- remove personal paths from the current files.

Record all three in the phase's review record.
