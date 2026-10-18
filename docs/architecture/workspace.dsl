/*
 * AdScout architecture as code: C4 model, context and container views (PROJECT.md §4).
 * Elements tagged "Planned" are not built yet; they are drawn dashed and grey and say which
 * phase adds them. No real publisher is named (PROJECT.md §1).
 *
 * Export (the gate fails until the stamp matches this file):
 *   java -jar structurizr-2026.09.19-playwright.war export -workspace docs/architecture/workspace.dsl -format svg -output docs/architecture/svg
 *   java -jar structurizr-2026.09.19-playwright.war export -workspace docs/architecture/workspace.dsl -format mermaid -output docs/architecture/mermaid
 *   uv run --locked python scripts/architecture.py stamp
 */
workspace "AdScout" "Advertiser prospecting and qualification agent (portfolio project)." {

    !identifiers hierarchical

    model {
        researcher = person "Ad sales researcher" "Works at a publisher; picks a segment, reviews the funnel and approves drafts."

        modelProvider = softwareSystem "Model provider" "Hosted language model API that scores fit and writes briefs and drafts (planned, Phase 2)." "External,Planned"
        enrichment = softwareSystem "Enrichment API" "Company-level facts such as size, category and region (planned, Phase 2)." "External,Planned"
        search = softwareSystem "Search API" "Web search for the read-only research agent (planned, Phase 3)." "External,Planned"
        websites = softwareSystem "Company websites" "Public pages the research agent reads as untrusted data (planned, Phase 3)." "External,Planned"
        crmSandbox = softwareSystem "CRM sandbox" "Free CRM test account that receives approved leads (planned, Phase 4)." "External,Planned"
        inbox = softwareSystem "Sandbox inbox" "Test inbox; the only place an approved message can go (planned, Phase 4)." "External,Planned"
        tracing = softwareSystem "Tracing service" "Traces of every step with tokens and cost per lead (planned, Phase 5)." "External,Planned"

        adscout = softwareSystem "AdScout" "Finds, scores and researches brands for one segment, drafts pitches for approval and syncs approved leads to a CRM." {
            pipeline = container "Command-line pipeline" "Sources seeds, runs each step (stubs in Phase 1), approves with a stub approver, syncs through the one CRM writer and checks every run." "Python CLI"
            config = container "Config files" "Segment rules, seed list and the stub script with its sources." "YAML and CSV files" "Files"
            database = container "Pipeline database" "Companies, leads with fixed source fields, step outcomes, drafts, approvals and run records." "SQLite file" "Database"
            fakeCrm = container "Local fake CRM" "Stand-in for the CRM sandbox until Phase 4: accounts, field owners and a write log." "SQLite tables" "Database"
            approvalUi = container "Approval queue" "Shows each draft with its brief; a person approves, edits or rejects (planned, Phase 4)." "Web app" "Planned"
            dashboard = container "Funnel dashboard" "Drop-off by step, cost per qualified lead and simulated revenue (planned, Phase 6)." "BI dashboard" "Planned"
        }

        researcher -> adscout.pipeline "Runs a segment and the stub approver" "Command line"
        researcher -> adscout.approvalUi "Approves, edits or rejects drafts" "Web browser" "Planned"
        researcher -> adscout.dashboard "Reviews the funnel and simulated revenue" "Web browser" "Planned"

        adscout.pipeline -> adscout.config "Reads segment rules, seeds and the stub script" "YAML, CSV"
        adscout.pipeline -> adscout.database "Stores leads, outcomes, drafts and run records" "SQL"
        adscout.pipeline -> adscout.fakeCrm "Writes approved leads through the one CRM writer" "SQL"
        adscout.approvalUi -> adscout.database "Reads drafts and records decisions" "SQL" "Planned"
        adscout.dashboard -> adscout.database "Reads the funnel views (read-only)" "SQL" "Planned"

        adscout.pipeline -> modelProvider "Scores fit, writes briefs and drafts" "HTTPS, JSON" "Planned"
        adscout.pipeline -> enrichment "Reads company facts" "HTTPS, JSON" "Planned"
        adscout.pipeline -> search "Searches the web (research agent, read-only)" "HTTPS, JSON" "Planned"
        adscout.pipeline -> websites "Fetches public pages (research agent, read-only)" "HTTPS" "Planned"
        adscout.pipeline -> crmSandbox "Writes approved leads through the one CRM writer" "HTTPS, REST" "Planned"
        adscout.pipeline -> inbox "Sends approved messages, sandbox only" "HTTPS or SMTP" "Planned"
        adscout.pipeline -> tracing "Sends step traces with tokens and cost" "OTLP" "Planned"
    }

    views {
        systemContext adscout "Context" "System Context diagram for AdScout (target; planned parts dashed; 2026-10-18)" {
            include *
            autolayout lr
        }

        container adscout "ContainersBuilt" "Container diagram for AdScout (built, Phase 1; 2026-10-18)" {
            include *
            exclude "element.tag==Planned"
            autolayout lr
        }

        container adscout "ContainersTarget" "Container diagram for AdScout (target; planned parts dashed; 2026-10-18)" {
            include *
            autolayout lr 700 120
        }

        styles {
            element "Element" {
                background #1168bd
                color #ffffff
            }
            element "Person" {
                shape person
                background #08427b
            }
            element "External" {
                background #999999
            }
            element "Database" {
                shape cylinder
            }
            element "Files" {
                shape folder
            }
            element "Planned" {
                background #f2f2f2
                color #555555
                stroke #999999
                border dashed
            }
            relationship "Relationship" {
                style solid
            }
            relationship "Planned" {
                style dashed
                color #999999
            }
        }
    }
}
