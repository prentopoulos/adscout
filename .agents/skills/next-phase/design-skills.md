# Design skills

Read this when a phase builds or changes something people look at: an app screen, a dashboard,
a public page or a chart. None of these skills is vendored into the project; each is installed
once per PC (below).

## Context first

Before choosing a skill, read the audience in PROJECT.md §1, the specs for the screens in
scope, the project's theme or design tokens, and any `.impeccable/` folder or DESIGN.md the
project has. Pin the look the owner asked for; reviewers critique its execution and do not
redirect it.

The constitution (PROJECT.md §5) outranks every design skill. A visual idiom must not make
the data claim more than it is.
- Simulated revenue is labelled as simulated on every chart, tile and table that shows it.
- Figures show measured values only; an unmeasured playbook target stays blank or TBD.
- Screens and demos use synthetic contacts; real company names appear only with public
  company-level data.

## Which skill

| Skill | Use it for | Limits |
|---|---|---|
| impeccable (`impeccable:impeccable`, plugin) | Shaping, critiquing, auditing and polishing product UI, dashboards included. It owns the critique method. | None beyond the constitution |
| ui-ux-pro-max (`ui-ux-pro-max:ui-ux-pro-max`, plugin) | Lookups: palettes, font pairings, chart types, UX and accessibility guidelines | If the project's stack is not one it lists, use its stack-neutral advice |
| dataviz (Claude Code built-in, when present) | Charts, stat tiles and palette validation, before writing chart code | None |
| tasteskill (`design-taste-frontend`, user skill) | Public-facing pages: landing, portfolio, product or demo pages | Not for dashboards or app screens; the skill says so itself |
| 21st.dev (`21st` MCP plugin, or the `21st-*` CLI skills) | Inspiration and React/Tailwind sketches | In another stack a sketch is a spec to rebuild, never pasted code. AI generation uses 21st credits; on a paid plan that is paid quota, so the spend ⛔ gate applies until the owner approves it. Prompts carry synthetic data only |
| design-eval (user skill, when installed) | A scored review (impeccable plus taste) before a UI PR is marked ready | For app screens, run it without the taste reviewer and say so |
| Figma skills (plugin) | Slides, mocks and FigJam boards | Load them before any Figma tool. Architecture diagrams default to code (showcase skill) |
| showcase (kit skill) | C4 diagrams as code, decks, walkthrough videos, READMEs, going public | The owner's wording rules: plain words, no taglines |

A skill recommendation does not justify adding its framework to the application. Changing the
UI stack is an owner decision recorded in PROJECT.md §4.

## Install on a new PC

- impeccable: `/plugin marketplace add pbakaus/impeccable`, then
  `/plugin install impeccable@impeccable`.
- ui-ux-pro-max: `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill`, then
  `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`.
- tasteskill (MIT): copy `skills/taste-skill/` and the root `LICENSE` from
  [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) at a pinned commit to
  `~/.claude/skills/design-taste-frontend/`, and record the commit. Its scripts need Node 22+
  and Chrome or Edge, and fetch pictures from open collections.
- 21st.dev MCP (ISC): `/plugin marketplace add 21st-dev/magic-mcp`, then
  `/plugin install 21st@21st-dev`. It connects to `https://21st.dev/api/mcp` with the key in the
  `API_KEY_21ST` environment variable, from https://21st.dev/settings/api-keys. Set it in the
  user environment, never in a repo. The CLI skills come from
  `npx @21st-dev/cli install-skill`.
