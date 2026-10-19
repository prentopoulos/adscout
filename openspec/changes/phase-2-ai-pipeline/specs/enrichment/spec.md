## ADDED Requirements

### Requirement: Polite fetcher
All page reads SHALL go through one fetcher that sends the User-Agent
`AdScoutBot/<version> (portfolio research bot; <contact>) httpx2/<version>` with the contact
from `ADSCOUT_CONTACT`; obeys robots.txt per RFC 9309 (a 5xx robots response disallows all,
401 and 403 read as disallow); waits at least 1 s per host or its Crawl-delay; sends GET
only, with no cookies or JavaScript; times out at 5 s connect and 15 s read; stops at 2 MB;
follows at most 3 redirects within the company's domain; does not retry 401 or 403; and
honours one Retry-After on 429. Every request SHALL write a `source_calls` row with its
robots decision and status.

#### Scenario: Robots disallow
- **WHEN** a fixture site's robots.txt disallows `/news`
- **THEN** the fetcher does not request `/news` and records the disallow

#### Scenario: Live without a contact
- **WHEN** a live run starts with `ADSCOUT_CONTACT` unset
- **THEN** it exits before any request and names the variable

### Requirement: Approved site list
Live enrichment SHALL read a company domain only when
`config/site-checks/<segment_id>.yaml` marks it `fetch`, with the robots and terms check
date and the owner's approval. A domain marked `skip` or missing SHALL exit the lead as
`missing_key_fields` with that reason, unless its key fields come from other sources.

#### Scenario: Unapproved domain
- **WHEN** a live run reaches a lead whose domain is not in the site list
- **THEN** no request goes to that domain and the outcome names the site list

### Requirement: Sources per field
Enrichment SHALL read at most 3 pages of the company's own site (home, newsroom or press,
store or shipping), Wikidata, SEC EDGAR for US filers and at most one web search per company
when launches are still empty. `ad_signals` SHALL come from deterministic detection of
ad-pixel and tag hosts in raw HTML; `categories`, `sells_in` and `recent_launches` from
Haiku extraction over page text. Each field SHALL store its value, source URL, source kind,
retrieval time and, for employee count and revenue, its as-of date. YouTube subscriber counts
SHALL NOT be stored.

#### Scenario: Field provenance
- **WHEN** enrichment of a fixture company finishes
- **THEN** every stored field has a source URL, source kind and retrieval time

#### Scenario: Pixel detection is deterministic
- **WHEN** a fixture page's HTML loads a known ad-tag host
- **THEN** `ad_signals` lists that tag without any model call

### Requirement: Field validation and key fields
Each field SHALL pass a validator before it is stored: ISO 3166-1 alpha-2 codes for
`sells_in` and `hq_country`; categories from the segment's list; employee count a positive
integer with an as-of date; revenue only for public companies, in USD with its period;
URLs absolute http(s). Invalid values SHALL be dropped with a recorded reason. A lead missing
`categories`, `sells_in` or `employee_count` SHALL exit as `missing_key_fields`.

#### Scenario: Invalid country code
- **WHEN** extraction returns `sells_in: ["USA", "CA"]`
- **THEN** `USA` is dropped with a reason and `CA` is kept

#### Scenario: Missing employee count
- **WHEN** no source yields an employee count for a lead
- **THEN** the lead exits at `enrich` as `missing_key_fields` naming the field
