# Two-account pull request flow

Basira development runs through pull requests on `main`, even for small changes. This note records how the flow works when the contributor and the reviewer are two different GitHub accounts.

## Roles

- **Contributor** (a collaborator account, for example the account that owns the feature work) opens the pull request from a short-lived branch.
- **Maintainer** (a second collaborator account with write access) reviews and merges.

## Flow

1. The contributor creates a branch from `main`, commits the change, and opens a pull request against `main`. The branch is deleted after merge.
2. CI runs on the pull request: frontend build, backend tests and the quality gate (see `.github/workflows/ci.yml`).
3. The maintainer reads the diff, checks the CHANGELOG line and the PLAN row if one applies, and submits an approving review. Comments go on the pull request, not in chat.
4. The maintainer merges with a merge commit once the review is in and checks are green. No force-pushes to shared branches, ever.
5. The contributor confirms `main` now contains the change before starting the next branch.

## Why two accounts

Keeping authorship and review on separate accounts makes the history honest: the person who wrote a change is never the person who approved it. That mirrors how an outside contributor would interact with the repo and keeps the review step real instead of ceremonial.
