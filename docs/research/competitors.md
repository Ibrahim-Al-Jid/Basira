# Competitor survey

Snapshot taken on 27 November 2026 from three public listings (checked by their publishers on 8 November 2026). The raw rows are in `competitors.json`. Facts here are only what those listings state. Nothing was run or tested by us.

Sources: https://aipentestingtools.com/open-source/ (20 open-source AI pentest agents), https://aipentestingtools.com/platforms/ (46 commercial platforms), https://appsecsanta.com/dast-tools/free-dast-tools (6 classic free DAST tools).

Total listed: 72. User estimate was about 60.

## What the field looks like

- Almost all of it tests live targets with active probing and exploit attempts. The platform listing says 45 of 46 commercial platforms test web apps and 33 publish a price.
- Findings are checked in very different ways, from a human reviewing every finding to no human at all.
- Published benchmark scores are self-reported by each project. The listing's own source says none was independently reproduced.

## Where Basira is different, and where it is not

- Basira reviews evidence the owner supplies (ZIP, GitHub snapshot, HAR, config, an approved page). It does not exploit anything. That is a safer scope and a narrower one: injection, XSS and access-control flaws that need live probing are listed as gaps in [taxonomy.md](../taxonomy.md).
- Findings are tied to redacted evidence, a location and a fix, and every check reports matched, clear, not applicable, skipped or error. Reports are bilingual (Arabic and English) with PDF.
- Not a claim: better detection than any listed tool. There is no head-to-head result yet. See [benchmarks.md](benchmarks.md) for how that gets measured.

## Open-source AI pentest agents

| Listing | Stars | Licence | Tests | Runs as | Paid edition |
|---|---|---|---|---|---|
| Strix (github.com/usestrix/strix) | 74,375 | Permissive Apache-2.0 | Web apps, APIs, Code | SaaS Self-hosted CLI Docker | Pro $29/seat/month, pentests billed separately (pay per test) |
| Shannon (github.com/KeygraphHQ/shannon) | 51,444 | Copyleft AGPL-3.0 | Web apps, APIs, Code | SaaS Self-hosted CLI Docker | Pro $50 per active developer/month |
| PentAGI (github.com/vxcontrol/pentagi) | 33,688 | Permissive MIT | Web apps, Networks | SaaS Self-hosted Docker | Yes, price not published |
| PentestGPT (github.com/GreyDGL/PentestGPT) | 16,325 | Permissive MIT | CTFs, Web apps, Networks | CLI Docker | — |
| HexStrike AI (github.com/0x4m4/hexstrike-ai) | 13,440 | Permissive MIT | Web apps, Networks, Cloud, CTFs | SaaS Self-hosted MCP | — |
| CAI (Cybersecurity AI) (github.com/aliasrobotics/cai) | 9,853 | Check terms see entry | Web apps, APIs, Networks, CTFs | CLI Library | Yes, price not published |
| Decepticon (github.com/BitterSecurity/Decepticon) | 6,568 | Permissive Apache-2.0 | Web apps, Networks, Active Directory, Cloud | SaaS Self-hosted CLI Docker MCP Library | Solo $19/month |
| Cairn (github.com/oritera/Cairn) | 4,945 | Copyleft AGPL-3.0 | Networks, CTFs | Docker | — |
| RedAmon (github.com/samugit83/redamon) | 3,329 | Permissive MIT | Web apps, APIs, Networks, LLM apps | SaaS Self-hosted Docker | — |
| PentestAgent (github.com/GH05TCREW/pentestagent) | 3,259 | Permissive MIT | Web apps, Networks | CLI Docker | — |
| Pentest Swarm AI (github.com/Armur-Ai/Pentest-Swarm-AI) | 3,153 | Copyleft AGPL-3.0 | Web apps, APIs, Networks, CTFs | CLI Docker | — |
| Guardian (github.com/zakirkun/guardian-cli) | 1,906 | Check terms MIT, with added authorised-use terms | Web apps, APIs, Networks, Active Directory, Cloud, Mobile, Code, LLM apps | CLI | — |
| Pentest-AI (github.com/0xSteph/pentest-ai) | 1,810 | Permissive MIT | Web apps | CLI MCP | — |
| Pentest Copilot (github.com/bugbasesecurity/pentest-copilot) | 1,553 | Permissive MIT | Web apps, Networks, CTFs | SaaS Self-hosted Docker | Yes, price not published |
| NeuroSploit (github.com/JoasASantos/NeuroSploit) | 1,507 | Permissive MIT | Web apps, Code, Networks, Active Directory, Cloud, LLM apps, Mobile | CLI | — |
| hackingBuddyGPT (github.com/ipa-lab/hackingBuddyGPT) | 1,307 | Permissive MIT | Networks, Web apps, APIs, Active Directory | CLI Library | — |
| DarkMoon (github.com/ASCIT31/Dark-Moon) | 1,209 | Copyleft GPL-3.0 | Web apps, APIs, Networks, Active Directory, Cloud | SaaS Self-hosted CLI Docker | Pro EUR 149 per month (or EUR 1,788 billed annually) |
| Nebula (github.com/berylliumsec/nebula) | 1,145 | Permissive BSD-2-Clause | Web apps, APIs, Networks | Desktop CLI | — |
| Villager (pypi.org) | — | Check terms see entry | Networks |  | — |
| WhiteRabbitNeo (now DeepHat) (deephat.ai) | — | Check terms see entry | — | Model | Yes, price not published |

## Commercial agentic and automated pentest platforms

| Listing (product, vendor) | Web | API | Network | AD | Cloud | LLM apps | Runs as | Price |
|---|---|---|---|---|---|---|---|---|
| Aikido AI Pentest Aikido Security | yes | yes | yes |  |  | yes | SaaS Self-hosted | Typical pentest $4,000 / €3,500 / £3,000 per assessment |
| Burp AT PortSwigger | yes | yes |  |  |  |  | Desktop | Public beta: $19 / $89 / $249 per user per month (Standard / |
| Ethiack Ethiack, S.A. | yes | yes | yes |  | yes |  | SaaS | Pentest from €3,000 per test |
| Hacktron Hacktron AI Inc. | yes |  |  |  |  |  | SaaS Self-hosted | Whitebox $50 to $25,000 per pentest (about $500 per 100,000  |
| Intruder AI Pentesting Intruder Systems Ltd | yes | yes |  |  |  |  | SaaS | $3,500 per test |
| Neo ProjectDiscovery | yes | yes | yes |  | yes |  | SaaS Self-hosted | Free $0 |
| Penligent Future Share LLC | yes | yes | yes |  |  |  | Self-hosted Desktop | Free $0 |
| Pentest-Tools.com AI Pentests (Specter) Pentest-Tools.com | yes |  |  |  |  |  | SaaS | $3,000 per application (AI Pentest, incl. 2 free retests) |
| Penti Penti | yes | yes | yes | yes | yes | yes | SaaS Self-hosted | Starter $20/mo |
| PurpleRidge Security Ridge Security | yes |  |  |  | yes |  | SaaS | Credit packs: Starter $399 (100 credits), Essential $1,699 ( |
| Siemba Autonomous Pentesting Siemba | yes | yes |  |  |  | yes | SaaS MCP | Autonomous Pentesting from $500/month (25 test runs/month) |
| TurboPentest IntegSec | yes | yes | yes |  | yes | yes | SaaS | $99 per pentest (Audit-Ready: 1 target, 4 agents) |
| XHack AI XHACK | yes | yes | yes | yes | yes | yes | SaaS Desktop | Individual AI plans $20 / $49 / $150 per month |
| Ares Assail, Inc. | yes | yes |  |  |  | yes | SaaS Self-hosted | No published subscription price (demo/contact) |
| Astra Autonomous Pentest (Pentest Auto) Astra IT, Inc. | yes | yes |  |  |  |  | SaaS | Pentest Auto $2,999/yr (1 target) |
| Beagle Security beaglesecurity.com | yes | yes |  |  |  |  | SaaS | Essential $119/month (2 tests/month), Advanced $359/month (1 |
| Cobalt Autonomous Pentest Cobalt | yes |  |  |  |  |  | SaaS | $3,500 per test, limited-time offer for web app tests starte |
| CodeAnt AI Pentesting CodeAnt AI, Inc. | yes | yes |  |  |  |  | SaaS | Not published |
| Decima Systems decima.systems | yes | yes |  |  |  |  | SaaS | Starter (early access): $99 per month: one target, one AI-ru |
| Escape AI Pentesting Escape Technologies | yes | yes | yes |  |  | yes | SaaS Self-hosted | On-Demand AI-Powered Pentest $3,000 (12-month contract) on E |
| FireCompass firecompass.com | yes | yes | yes | yes |  | yes | SaaS Self-hosted | Not published |
| HackerAI HackerAI LLC |  |  |  |  |  |  | SaaS Desktop CLI | Free $0 |
| Helix Cyber HelixML, Inc. | yes | yes | yes |  | yes | yes | SaaS | Black box $3,000 |
| Invicti Agentic Pentest Invicti Security | yes | yes |  |  |  |  | SaaS | $500 max per pentest (one application and its API suite) |
| Nova Hadrian | yes |  |  |  |  |  | SaaS | From €1,250 per test excluding VAT |
| Ostorlab Agentic Deep Scan (Agentic Pentest) Ostorlab | yes | yes | yes |  |  |  | SaaS Self-hosted | Agentic Pentest one-time: Core $500, Advanced $2,000, Elite  |
| Penetrify Algofy s.r.o. | yes | yes |  |  |  |  | SaaS | Starter $100/mo (1 test) |
| Pensar PensarAI, Inc. | yes | yes |  |  |  |  | SaaS CLI | Not published |
| Sable Vulnetic Inc. | yes | yes | yes | yes | yes |  | SaaS Self-hosted Docker | Practitioner $300/mo (web app, API, network and AD assessmen |
| Sara Pentest Synack | yes |  | yes |  |  |  | SaaS | From $5,085 for 1 Standard Sara Pentest (one-time or recurri |
| Simbian AI Pentest Agent Simbian, Inc. | yes |  |  |  |  |  | SaaS Self-hosted | Not published |
| Snipe Stingrai Inc. | yes | yes |  |  |  | yes | SaaS | Autonomous Pentest $3,000 per assessment (one web app + APIs |
| StealthNet AI stealthnet.ai | yes | yes | yes |  |  | yes | SaaS | StealthStrike (AI-only) $1,500 for a single small scope |
| XBOW XBOW | yes | yes |  |  |  |  | SaaS | Quote-based, usage-based |
| Breach360 BreachLock | yes | yes | yes |  |  |  | Self-hosted CLI Docker | Not published |
| Bright AI Pentesting (AI PT) Bright Security | yes | yes |  |  |  |  | SaaS | Not published |
| NodeZero Horizon3.ai | yes | yes | yes | yes | yes |  | SaaS Self-hosted Docker | Per asset, 12-month term: Flex $15 per asset per test |
| Novee Novee Security | yes | yes |  |  |  | yes | SaaS Self-hosted | Not published |
| Pentera Pentera | yes | yes | yes | yes | yes |  |  | No price on its own site |
| RidgeBot Ridge Security | yes | yes | yes | yes |  |  | SaaS Self-hosted | Not published |
| RidgeGen Ridge Security | yes | yes | yes | yes |  |  | Self-hosted | Not published |
| Snyk Evo Continuous Offensive Security Snyk | yes | yes |  |  |  | yes | SaaS | 4,000 credits per assessment (1 credit = $1) |
| Sybil RunSybil | yes | yes |  |  | yes |  | SaaS | Not published |
| Terra Platform Terra Security | yes | yes | yes |  | yes | yes | SaaS Self-hosted | Not published |
| Equixly equixly.com | yes | yes |  |  |  | yes | SaaS | Not published |
| Prancer (SwarmHack) Prancer | yes | yes | yes | yes | yes | yes | SaaS Self-hosted | Not published |

## Classic open-source DAST scanners

| Tool | Licence |
|---|---|
| OWASP ZAP | Apache-2.0 |
| Nuclei | MIT |
| Nikto | GPL |
| Wapiti | GPL |
| Arachni (archived) | not stated |
| w3af (limited maintenance) | not stated |
