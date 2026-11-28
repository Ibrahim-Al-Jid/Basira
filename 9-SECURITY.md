# Security policy

Basira reviews other projects for security problems, so reports about Basira itself are welcome and should stay private until there is a fix.

## Reporting a vulnerability

Report privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** (a private advisory). If that form is unavailable, reach the repository owner through their GitHub profile and ask for a private channel first. Please do not open a public issue, pull request or discussion for a security problem.

Include what makes the report reproducible: the affected commit or version, the endpoint or file, the request or input that triggers it, and what an attacker gains. Do not send real user data, live credentials or working exploit code against systems you do not own.

## What is in scope

- The application in this repository: the HTTP API, the scan pipeline, the isolated worker, the report and export paths, and the personal workspace (accounts, projects, the GitHub authorization).
- The checks in `backend/checks/` and the taxonomy behind them, when a check reports something that would mislead the person reading the report.
- The build and deployment configuration kept here: `Dockerfile`, the Compose files, the CI workflow and the scripts in `ops/`.

## What is not in scope

- Findings Basira reports about a third-party project. Those go to that project's maintainers.
- Denial of service through deliberately huge inputs, or resource exhaustion in your own local environment.
- Anything that needs a modified server, browser or operating system on the user's side.
- Missing hardening that the deployment documentation already lists as the operator's responsibility.
- A vulnerable dependency with no path to reach it through Basira. Report it upstream, and tell us if you think Basira is affected.

## What to expect

One maintainer, best effort: an acknowledgement when the report arrives, an assessment once it is reproduced, and a note when a fix ships. There is no paid bounty and no fixed response time. Please give a fix a reasonable window before publishing; you are credited in the changelog unless you ask not to be.

## Supported versions

`main` and the latest tagged release. Older commits and local forks are not supported.
