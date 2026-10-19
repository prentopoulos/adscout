## ADDED Requirements

### Requirement: Lead and fixed roster of workers
Research SHALL run only for qualified leads. Code SHALL dispatch three workers (audience and
channels; ad activity; recent launches and sponsorships) in parallel. A lead plan call with
no tools SHALL write 1–3 questions per worker; seed URLs SHALL be attached by code from
enrichment, never by a model. A lead merge call with no tools SHALL see verified claims only
and write summary points, each citing claim IDs.

#### Scenario: Roster fixed in code
- **WHEN** the plan output asks for a fourth worker or names a URL
- **THEN** the extra worker is not run and the URL is not attached

### Requirement: Worker tools and caps
Each worker SHALL hold exactly `web_search` (server tool `web_search_20250305`, direct
callers only, `max_uses` set, blocked domains, US location), `fetch_page` and
`submit_findings`, and SHALL stop at 6 model calls, 3 searches, 2 pages, 90 s or its cost cap,
whichever comes first, recording why it stopped. Per lead, research SHALL stop at 20 calls, 9
searches, 6 pages and its cost cap.

#### Scenario: Page budget
- **WHEN** a fake worker requests a third page
- **THEN** `fetch_page` refuses it, and the worker's findings record the page cap

### Requirement: Fetch provenance
`fetch_page` SHALL accept a URL only if it appeared in this worker's search results, the
lead's seed URLs or a same-site link on the company's domain, and SHALL refuse non-http(s)
schemes, IP literals, private address ranges, credentials in the URL and query strings over
the configured length. It SHALL use the polite fetcher and return text trimmed to about 4K
tokens.

#### Scenario: URL from page text refused
- **WHEN** a fake worker asks to fetch a URL that appeared only inside a fetched page's text
- **THEN** the fetch is refused and recorded, and no request is sent

### Requirement: Verified claims only
A worker's claim SHALL be kept only if its source URL equals, after normalization, a URL
fetched successfully in this run; its quote of at least 20 characters appears in that page's
text after NFKC, whitespace and case normalization; and every number in the claim appears in
the quote. Claims SHALL be stored in `claims` with quotes of at most 300 characters and the
verifier version. The merge SHALL cite only verified claim IDs and use no number absent from
them. Dropped claims SHALL be counted.

#### Scenario: Quote not on the page
- **WHEN** a claim's quote does not appear in the fetched text of its URL
- **THEN** the claim is dropped, counted, and absent from the brief

#### Scenario: Verifier case set
- **WHEN** the gate runs the verifier cases
- **THEN** every case's expected keep or drop matches

### Requirement: Brief outcomes
A brief SHALL record its status, design (`multi` or `single`), caps hit and gaps. A lead with
no verified claim, or whose workers all failed, SHALL exit as `research_failed` for a person.
A brief with any cap hit, failed worker or uncovered topic SHALL be kept with the flag
`research_partial`.

#### Scenario: All workers fail
- **WHEN** every fake worker returns an error
- **THEN** the lead exits as `research_failed` and no draft is written

### Requirement: Single-agent baseline and comparison
`--research-design single` SHALL run one Sonnet agent with the same tools, verifier, output
schema and total budget (9 searches, 6 pages, 12 steps). The design comparison SHALL follow
the plan committed under `evals/plans/` before measuring, and its report SHALL include every
repeat.

#### Scenario: Same budget for both designs
- **WHEN** both designs research the same fixture lead
- **THEN** their search, page and step caps are equal
