## MODIFIED Requirements

### Requirement: Segment config file
Each segment SHALL be defined in one YAML file `config/segments/<segment_id>.yaml`, loaded
with a safe YAML loader and validated by a strict model that rejects unknown fields. The
config SHALL carry a schema version, a segment ID (lowercase slug matching the file name), a
name, a one-sentence scope, regions as ISO 3166-1 alpha-2 codes, allowed categories, a size
range, exclusions (domains and categories), a score threshold, a near-miss band, and score
criteria with anchors and weights that sum to 1. A field the segment has not decided yet
SHALL be null with a reason, never a guessed value.

#### Scenario: Valid config loads
- **WHEN** `config/segments/gaming-hardware-na.yaml` is loaded
- **THEN** it validates, its regions are `US` and `CA`, its size range is at least 50
  employees with no maximum, its threshold is 60, its near-miss band is 55–59, and its
  weights are audience 0.35, ad activity 0.30, budget capacity 0.20 and recent launches 0.15

#### Scenario: Weights must sum to 1
- **WHEN** a config's criterion weights sum to 0.95
- **THEN** loading fails and names the weights

#### Scenario: Unknown field rejected
- **WHEN** a segment config contains a field the model does not define
- **THEN** loading fails and the error names the field

#### Scenario: YAML coercion trap
- **WHEN** a region is written unquoted as `NO`
- **THEN** loading fails instead of reading it as a boolean

#### Scenario: Null without a reason
- **WHEN** a nullable field is null and has no entry in the config's null reasons
- **THEN** loading fails and names the field
