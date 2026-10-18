# C4 diagrams in FigJam

These conventions come from the C4 model's notation guide
([c4model.com/diagrams/notation](https://c4model.com/diagrams/notation)). The technique was
worked out on the Compute Cost & Risk Monitor diagrams (October 2026).

## What engineers expect

| Rule | Example |
| --- | --- |
| A title with the type and scope | "System Context diagram for Compute Cost & Risk Monitor (2026-10-15)" |
| A key on every diagram | "Key: blue = a container in this system (cylinder = data store) · white = person or external system · arrow = who acts on whom, labelled with what it does and [technology]" |
| Name, [type: technology] and one line of description on each element | "Collector [Container: Python CLI] / Fetches Azure's GPU list prices and saves every response." |
| Lines go one way, with a specific verb and the technology | "Reads list prices / [HTTPS, JSON]", "Stores price rows / [SQL]" |
| Containers run or store data | apps, CLIs, databases and file stores. Fold modules (a calculator, a schema helper, a checker) into their container's description |
| The same colours mean the same thing in every view | blue = this system or its containers; white = people and external systems |
| About 15–20 elements at most | split the diagram if it grows past that |

**A context view** shows the people, the system as one box, and the external systems.
**A container view** shows the programs and data stores inside the system's boundary, the
same people, and the external systems.

## Default: Structurizr DSL (diagrams as code)

One model generates every view, so the views can't disagree, and the model is reviewed in pull
requests like code. Check the current commands with Context7 (`/websites/structurizr`) before
relying on them; this page was checked on 2026-10-15.

A starter `docs/architecture/workspace.dsl`:

```text
workspace "Example system" "One-line purpose." {
    model {
        user = person "GPU buyer" "Sizes a GPU workload and its budget."
        api = softwareSystem "Azure Retail Prices API" "Microsoft's published list prices." "External"
        system = softwareSystem "Example system" "What it does, in one line." {
            cli = container "Collector" "Fetches list prices and saves every response." "Python CLI"
            app = container "Dashboard" "Shows costs and what-if moves." "Streamlit web app"
            db = container "Database" "Collected prices." "DuckDB file" "Database"
        }
        user -> app "Compares options and sizes costs" "Web browser"
        cli -> api "Reads list prices" "HTTPS, JSON"
        cli -> db "Stores price rows" "SQL"
        app -> db "Reads prices (read-only)" "SQL"
    }
    views {
        systemContext system "Context" "System Context diagram for Example system" {
            include *
            autolayout lr
        }
        container system "Containers" "Container diagram for Example system" {
            include *
            autolayout lr
        }
        styles {
            element "Element" { background #1168bd color #ffffff }
            element "Person" { shape person background #08427b }
            element "External" { background #999999 }
            element "Database" { shape cylinder }
        }
    }
}
```

The three strings on a container are its name, description and technology. Relationships take
a verb label and a technology. Structurizr draws the key itself.

- **View and arrange it locally:**

  ```sh
  docker run -it --rm -p 127.0.0.1:8080:8080 -v "$PWD/docs/architecture:/usr/local/structurizr" structurizr/structurizr local
  ```

  Then open http://localhost:8080. The `127.0.0.1:` prefix keeps it off the network.
- **Export:** Structurizr's `export` command writes `-format svg` or `png` (images for `docs/`),
  `mermaid` (for the README) and `plantuml/c4plantuml`. See docs.structurizr.com/export for the
  exact invocation of the current release.
- **Without Docker (checked 2026-10-18):** current Structurizr releases need Java 21, and only
  the `-playwright` builds export SVG or PNG. Unzip Microsoft's OpenJDK 21 into a user folder
  (no installer, no PATH change), download `structurizr-<version>-playwright.war` outside the
  repository, then run, from the repository root:

  ```sh
  java -jar structurizr-<version>-playwright.war validate -workspace docs/architecture/workspace.dsl
  java -jar structurizr-<version>-playwright.war export -workspace docs/architecture/workspace.dsl -format svg -output docs/architecture/svg
  java -jar structurizr-<version>-playwright.war export -workspace docs/architecture/workspace.dsl -format mermaid -output docs/architecture/mermaid
  ```

  `validate` prints errors but exits 0, so read its output. The first SVG export downloads a
  Playwright browser (WebKit, about 60 MB) to the user profile. `-format png` into a scratch
  folder gives images to inspect the layout. AdScout's `scripts/architecture.py stamp` then
  records the export so its gate can tell when the model changed without a re-export.
- **Mermaid in the README:** paste the exported definition into a fenced code block marked
  `mermaid`, and GitHub renders it. Mermaid's own C4 syntax is still experimental, so prefer
  exporting from the Structurizr model.
- **Spacing:** use `autolayout lr` first. If labels collide, raise the rank and node separation
  (`autolayout lr 300 300`), or arrange the view by hand in the local editor; the layout is saved
  with the workspace.

## Alternative: FigJam technique (`use_figma` with the figma-use-figjam skill)

Use this only when the owner wants the diagrams on a Figma board.

- **Start from the board's nodes.** Read the IDs with `get_figjam`. For a large board, grep the
  saved output for `<section`.
- **Make new boxes and lines by cloning** existing styled ones (`node.clone()`, then append to the
  right section), so that fonts, fills and strokes match.
- **Load the font before any text edit** (`Inter Medium` on these boards). Connector text is
  `connector.text.characters`.
- **Use straight connectors pinned to sides:** `connectorLineType = "STRAIGHT"`, start magnet
  `RIGHT`, end magnet `LEFT`, and `dashPattern = []`. Elbowed lines with automatic magnets pile
  their labels into the same corridor.
- **Use two-line labels:** the action on the first line, `[technology]` on the second. They fit
  gaps that a one-line label overruns.
- **Lay out so the labels stay apart.**
  - Put programs in a left column and data stores in a right column, with a wide gap (about
    600 px) between them.
  - A straight line's label sits at its midpoint. Compute the midpoint height of every line and
    space the rows until consecutive midpoints are at least about 100 px apart.
  - Line each external system up with the box that calls it, so its line runs level and
    crosses nothing.
- **Space evenly, and measure it.**
  - Set the gaps between columns to the same value, e.g. 370 px in a context view or 240 px
    either side of the system boundary.
  - Use the same left and right margins.
  - Space same-kind rows evenly (programs 240 px apart, data stores evenly between them).
  - Centre each box between the boxes it connects.
  - Have the script return the gaps (`b.x - (a.x + a.width)`) and margins, and check that they
    match.
- **Add the key** with `figma.createText()` inside the section: append it first, then set `x` and
  `y`.
- **Screenshot after every change** (`await section.screenshot({ scale: 0.4 })`) and fix
  overlaps before exporting.
- **Export** each view with `download_assets` (`defaultFormat: "svg"`). Download it to a
  scratch folder, check it starts with `<svg` and contains no `<script`, then copy it into the
  repository's `docs/architecture/`.
