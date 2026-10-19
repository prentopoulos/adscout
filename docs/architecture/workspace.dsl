/*
 * AdScout architecture as code: C4 model with context, container and component views
 * (PROJECT.md §4). Elements tagged "Planned" are not built yet; they are drawn dashed and grey
 * and say which phase adds them. No real publisher is named (PROJECT.md §1). The agent-level
 * flow is generated from the agent registry instead (agents.md, agent-flow.html).
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

        modelProvider = softwareSystem "Model provider" "Anthropic's Messages API: field extraction, scoring, the research team and the draft loop." "External"
        search = softwareSystem "Web search" "The model provider's server-side search tool; results are untrusted text." "External"
        enrichment = softwareSystem "Public data APIs" "Wikidata and SEC EDGAR: company size, region and filings; no key needed." "External"
        websites = softwareSystem "Company websites" "Public pages, read politely (robots.txt, a delay per host) as untrusted data." "External"
        crmSandbox = softwareSystem "CRM sandbox" "Free CRM test account that receives approved leads (planned, Phase 3)." "External,Planned"
        inbox = softwareSystem "Sandbox inbox" "Test inbox; the only place an approved message can go (planned, Phase 3)." "External,Planned"
        tracing = softwareSystem "Tracing service" "Traces of every step with tokens and cost per lead (planned, Phase 3)." "External,Planned"

        adscout = softwareSystem "AdScout" "Finds, scores and researches brands for one segment, drafts pitches for approval and syncs approved leads to a CRM." {
            pipeline = container "Command-line pipeline" "Runs a segment through enrichment, rules, scoring, the research team and the draft loop; leads stop at approval. Checks and traces every run." "Python CLI" {
                adapter = component "Model adapter" "Every model call: the registry's tool allowlist, the price table, a spend reservation and a record per call." "Python"
                fetcher = component "Polite fetcher" "robots.txt, a delay per host, a 2 MB cap and egress rules; refuses unsafe URLs before any request." "Python"
                lead = component "Research lead" "Plans the workers' questions, then merges verified claims into a brief." "Sonnet agent, no tools" "Agent"
                audience = component "Audience worker" "Researches the company's audience and channels." "Haiku agent: search, fetch" "Agent"
                ads = component "Ad-activity worker" "Researches where and how the company advertises." "Haiku agent: search, fetch" "Agent"
                launches = component "Launches worker" "Researches recent launches and sponsorships." "Haiku agent: search, fetch" "Agent"
                verifier = component "Claim verifier" "Keeps a claim only if its page was fetched in this run, its quote is on the page and it carries no link or person." "Python"
                writer = component "Draft writer" "Writes a pitch whose every factual sentence cites a verified claim or a simulated media-kit fact." "Sonnet agent, no tools" "Agent"
                ruleChecker = component "Rule checker" "Supports, numbers, names, links, length and footer; no personal data." "Python"
                critic = component "Draft critic" "Judges relevance, specificity, tone and the ask; cannot pass a draft the rules fail." "Sonnet agent, no tools" "Agent"
            }
            config = container "Config files" "Segment rules, seed list, site list, media kit and price table." "YAML and CSV files" "Files"
            database = container "Pipeline database" "Companies, leads, enriched fields, scores, claims, drafts, approvals, spans and every model and source call." "SQLite file" "Database"
            fakeCrm = container "Local fake CRM" "Local sandbox: accounts, field owners and a write log; no external service." "SQLite tables" "Database"
            workspace = container "Local workspace" "Human review, CRM sync, local sandbox inbox and funnel with simulated revenue. Binds approval to draft text; unsubscribe blocks later local delivery." "Python HTTP on 127.0.0.1"
        }

        researcher -> adscout.pipeline "Runs a segment, traces and checks runs" "Command line"
        researcher -> adscout.workspace "Reviews drafts and the funnel; approves sandbox actions" "HTTP on loopback"

        adscout.pipeline -> adscout.config "Reads segment rules, seeds, sites, the media kit and prices" "YAML, CSV"
        adscout.pipeline -> adscout.database "Stores leads, outcomes, claims, drafts and call records" "SQL"
        adscout.pipeline -> adscout.fakeCrm "Writes approved leads through the one CRM writer" "SQL"
        adscout.workspace -> adscout.database "Reads evidence, records approvals, local messages and simulated deals" "SQL"
        adscout.workspace -> adscout.fakeCrm "Syncs approved records through the one CRM writer" "SQL"

        adscout.pipeline -> enrichment "Reads company facts" "HTTPS, JSON"
        adscout.pipeline -> search "Searches through the model's server tool (research workers, launch search)" "HTTPS, JSON"
        adscout.pipeline -> crmSandbox "Writes approved leads through the one CRM writer" "HTTPS, REST" "Planned"
        adscout.pipeline -> inbox "Sends approved messages, sandbox only" "HTTPS or SMTP" "Planned"
        adscout.pipeline -> tracing "Sends step traces with tokens and cost" "OTLP" "Planned"

        adscout.pipeline.lead -> adscout.pipeline.audience "Sends a WorkerTask" "in process"
        adscout.pipeline.lead -> adscout.pipeline.ads "Sends a WorkerTask" "in process"
        adscout.pipeline.lead -> adscout.pipeline.launches "Sends a WorkerTask" "in process"
        adscout.pipeline.audience -> adscout.pipeline.verifier "Hands WorkerFindings to" "in process"
        adscout.pipeline.ads -> adscout.pipeline.verifier "Hands WorkerFindings to" "in process"
        adscout.pipeline.launches -> adscout.pipeline.verifier "Hands WorkerFindings to" "in process"
        adscout.pipeline.audience -> adscout.pipeline.fetcher "Reads pages through" "fetch_page"
        adscout.pipeline.ads -> adscout.pipeline.fetcher "Reads pages through" "fetch_page"
        adscout.pipeline.launches -> adscout.pipeline.fetcher "Reads pages through" "fetch_page"
        adscout.pipeline.verifier -> adscout.pipeline.lead "Passes verified claims to" "in process"
        adscout.pipeline.lead -> adscout.pipeline.writer "Passes the brief to" "in process"
        adscout.pipeline.writer -> adscout.pipeline.ruleChecker "Passes each draft to" "in process"
        adscout.pipeline.ruleChecker -> adscout.pipeline.critic "Passes a rule-clean draft to" "in process"
        adscout.pipeline.critic -> adscout.pipeline.writer "Returns issues for a rewrite (at most 2)" "in process"
        adscout.pipeline.lead -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.audience -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.ads -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.launches -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.writer -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.critic -> adscout.pipeline.adapter "Calls the model through" "in process"
        adscout.pipeline.adapter -> modelProvider "Sends checked requests" "HTTPS, JSON"
        adscout.pipeline.fetcher -> websites "Fetches public pages" "HTTPS"
    }

    views {
        systemContext adscout "Context" "System Context diagram for AdScout (target; planned parts dashed; 2026-10-19)" {
            include *
            autolayout lr
        }

        container adscout "ContainersBuilt" "Container diagram for AdScout (built, Phase 2; 2026-10-19)" {
            include *
            exclude "element.tag==Planned"
            autolayout lr
        }

        container adscout "ContainersTarget" "Container diagram for AdScout (target; planned parts dashed; 2026-10-19)" {
            include *
            autolayout lr 700 120
        }

        component adscout.pipeline "ResearchTeam" "Component diagram: the research team and the draft loop (built, Phase 2; 2026-10-19)" {
            include *
            autolayout lr 300 120
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
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Agent" {
                background #0d7a6f
                color #ffffff
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
