# 7. Slides outline and speaker notes

Target: 20 minutes of talk, 10 minutes of live demo, questions after. Every number on a slide must match [evaluation.md](evaluation.md). Slides are built from this outline after the owner confirms the story; the deck itself is a separate file.

| # | Slide | Content | Say | Min |
|---|---|---|---|---|
| 1 | Title | Basira (بصيرة): multi-agent security review of project files | name, supervisor, one sentence of the project | 0.5 |
| 2 | Problem | manual review slow, scanners noisy, AI pentest agents need live-target trust | why a student team cannot hand a tool its live system | 1.5 |
| 3 | Idea | review evidence the owner supplies; never exploit | narrower and safer on purpose | 1 |
| 4 | Related work | 72 tools surveyed; almost all probe live targets | what is different, and what is not claimed | 1.5 |
| 5 | What Basira does | intake, 100 checks, five roles, bilingual reports | one picture of the flow | 1.5 |
| 6 | Architecture | five LangGraph roles, model is advisory, deterministic fallback | accepted whole or rejected whole | 2 |
| 7 | Data and safety | ownership checks, lease and outbox, key encryption, URL checks | one crash-safety example | 1.5 |
| 8 | Taxonomy | 17 domains, 75 subdomains, 34 covered, 41 gaps | honest map of what is not covered | 1 |
| 9 | Evaluation method | DVWA pinned commit, 13 vulnerable and 13 fixed files, four configurations | how a hit is counted | 1.5 |
| 10 | Results | C1 0 of 13; C2 8 of 13 with 5 of 13 clean files flagged; C3, C4 not run | read the weak numbers aloud, then limits | 2 |
| 11 | Limits | one labeler, one model, one run, free tier, n = 13 | what this cannot claim | 1.5 |
| 12 | Ethics | owner-supplied evidence, active probing only for owner-proven targets | rules 1 to 4 | 1 |
| 13 | Usability | fill from real sessions only (state "not run" if not done) | do not show an empty table as a result | 1 |
| 14 | Demo | see below | switch to the live app | 10 |
| 15 | Future work | source-code checks (P19), precision gate (P23), recheck (P11), team configs (P17) | next measured step | 1 |
| 16 | Close | the one-sentence result | what was learned | 0.5 |

## Demo script

Follow [DEMO.md](../DEMO.md) exactly: empty project, start scan, lanes fill one by one, step-by-step findings, report coverage, export PDF and JSON, switch to Arabic, then the recorded numbers. Have the pre-run report open in a second tab. If the model provider is down, say the deterministic path is by design.

## Before the day

Rehearse on the demo machine and network (not done yet), check free quota on the key, pre-run the scan once, and keep PDF and JSON exports on disk.
