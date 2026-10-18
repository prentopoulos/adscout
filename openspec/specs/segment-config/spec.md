# segment-config Specification

## Purpose
One validated config per segment and its seed list, holding company-level data only,
with content hashes that tie every run to exactly what it used.

## Requirements
### Requirement: Segment config file
Each segment SHALL be defined in one YAML file `config/segments/<segment_id>.yaml`, loaded
with a safe YAML loader and validated by a strict model that rejects unknown fields. The
config SHALL carry a schema version, a segment ID (lowercase slug matching the file name), a
name, a one-sentence scope, regions as ISO 3166-1 alpha-2 codes, allowed categories, a size
range, exclusions (domains and categories) and a score threshold. A field the segment has not
decided yet SHALL be null with a reason, never a guessed value.

#### Scenario: Valid config loads
- **WHEN** `config/segments/gaming-hardware-na.yaml` is loaded
- **THEN** it validates, its regions are `US` and `CA`, and its size range and score
  threshold are null, each with the reason "set in Phase 2 grilling"

#### Scenario: Unknown field rejected
- **WHEN** a segment config contains a field the model does not define
- **THEN** loading fails and the error names the field

#### Scenario: YAML coercion trap
- **WHEN** a region is written unquoted as `NO`
- **THEN** loading fails instead of reading it as a boolean

#### Scenario: Null without a reason
- **WHEN** a nullable field is null and has no entry in the config's null reasons
- **THEN** loading fails and names the field

### Requirement: Seed list file
Each segment's seed list SHALL be one CSV file `config/seeds/<segment_id>.csv` with exactly
the columns `name`, `domain`, `source`, `added_by`, `added_on` and `notes`, validated row by
row. Domains SHALL be normalized (lowercase; scheme, path, port, trailing dot and a leading
`www.` removed) and non-ASCII domains rejected. Duplicate domains in one file SHALL be
reported, not silently merged.

#### Scenario: Valid seed list loads
- **WHEN** `config/seeds/gaming-hardware-na.csv` is loaded
- **THEN** it yields five rows with normalized domains and a source on every row

#### Scenario: Extra column rejected
- **WHEN** a seed file has a column outside the allowed six
- **THEN** loading fails and names the column

#### Scenario: Domain normalized
- **WHEN** a row's domain is `https://WWW.Example.test:443/shop/`
- **THEN** the loaded domain is `example.test`

### Requirement: Company-level data only
Config and seed values SHALL NOT contain personal contact data. Loading SHALL fail when any
string value parses as an email address or a phone number.

#### Scenario: Email in a seed row
- **WHEN** a seed row's notes contain `jane@example.com`
- **THEN** loading fails and names the row and column without printing the value

#### Scenario: Phone number in a config
- **WHEN** a segment config description contains `+1 514 555 0100`
- **THEN** loading fails

### Requirement: Committed schemas
The segment config and seed row formats SHALL each be exported from their models to a
committed JSON Schema (Draft 2020-12) under `config/schemas/`, and the gate SHALL fail when an
export differs from its committed file.

#### Scenario: Schema drift
- **WHEN** the segment config model changes without regenerating its schema file
- **THEN** the gate fails

### Requirement: Content hashes
The system SHALL compute `icp_config_hash` and `seed_list_hash` as the SHA-256 of the
canonical JSON of the validated content, so formatting and comment edits do not change them,
and SHALL store each hashed content snapshot in the database the first time a run uses it.

#### Scenario: Comment edit keeps the hash
- **WHEN** only a YAML comment in the segment config changes
- **THEN** `icp_config_hash` is unchanged

#### Scenario: Value edit changes the hash
- **WHEN** one allowed category is added
- **THEN** `icp_config_hash` changes

### Requirement: Seed provenance
Every seed row SHALL record where it came from and who added it and when. For the Phase 1
seeds, each domain SHALL have been checked once against the company's own home page under the
owner's recorded live-read decision, and the row's notes SHALL say so with the date.

#### Scenario: Phase 1 seed rows
- **WHEN** the Phase 1 seed file is read
- **THEN** every row has a non-empty source, `added_by` and `added_on`, and its notes record
  the home-page check

