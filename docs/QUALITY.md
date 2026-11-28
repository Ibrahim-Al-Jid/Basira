# Quality gates

Detection rate alone rewards noisy checks. Every measured set records three numbers, and a change fails when recall or precision drops or the false-positive rate rises. Plan item: P23 in [PLAN.md](PLAN.md).

## What is measured

| Set | Input | Needs network | Baseline (27 Nov 2026) |
|---|---|---|---|
| `reference_corpus` | 12-case regression corpus, static adapters, mocked profile | no | precision 0.900, recall 0.900 (9 true, 1 false, 1 missed) |
| `dvwa_static` | 13 vulnerable and 13 fixed DVWA files at a pinned commit, static checks only | yes | recall 0.615 (8 of 13), precision 0.533, false-positive rate 0.077 (1 of 13 clean files flagged); after P19, a development score (source: `tests/fixtures/quality-baseline.json`) |
| `dvwa_model_single_recorded` | the recorded C2 model run scored against the same DVWA labels | no | recall 0.615 (8 of 13), precision 0.250, false-positive rate 5 of 13 clean files |

The reference corpus was written together with the checks, so it guards against regressions and proves little about detection. DVWA is the independent set; its labels come from one reader. The unit is a (file, taxonomy subdomain) pair. A pair reported anywhere other than a labeled vulnerability is a false positive, including the same subdomain on a fixed file. The false-positive rate is fixed files flagged divided by fixed files. The mocked profile simulates the external adapters, so its numbers are not a claim about the real tools.

## Model configurations

`dvwa_model_single_recorded` scores the recorded C2 run (`docs/research/detection-runs/2026-11-27-single-findings.json`) against the same pinned labels. It runs offline in every gate run: no provider call, no download. It guards the scoring code and the recorded file; it does not prove the model is still this good. A new run is recorded by replacing the findings file in a change that also updates the baseline and says why. C3 and C4 get a set here when they have a recorded run.

## Run it

```
python -m backend.quality_gate            # offline corpus, exit 1 on a regression
python -m backend.quality_gate --network  # also DVWA (downloads the pinned files, checks digests)
python -m backend.quality_gate --print    # print current numbers, compare nothing
pytest backend/test_quality_gate.py       # same gate through pytest; set BASIRA_EVAL_NETWORK=1 for DVWA
```

The baseline is `tests/fixtures/quality-baseline.json`. Improvements never fail. Raise the baseline in the same change that earns the improvement, with the printed numbers in the changelog line. Never lower it to make a change pass; a lower number needs the owner's decision recorded in the plan.

## Browser suites

Five Playwright suites run on every pull request, in the `Browser smoke and container acceptance` job in `.github/workflows/ci.yml`, against a real Compose deployment:

- Personal projects: ZIP scan and report in personal mode (runs right after the browser smoke).
- Account: invitations, access and credentials.
- Workspace: routing and report scope.
- Password: signup, sign-in and cross-account isolation, with password auth and self-signup switched on.
- Source intake: source intake and linked evidence (`tests/browser_source_intake.py`, added to CI in #155).

They need Docker and Chromium, so they are not part of `pytest backend`. A suite that fails here blocks the merge.

## Flaky tests

A test that fails and then passes with no code change is a defect, not noise.

1. Never re-run until green. Record the test name and the failure in the pull request that found it.
2. Fix it within the same pull request when the cause is clear (time, ordering, shared state, network).
3. If it cannot be fixed now, mark it `@pytest.mark.skip(reason="flaky: <cause>, owner: <name>, <date>")`, and add a line to the plan under the owning phase. A skip without a reason, owner and date is not accepted.
4. Tests that need the network or external tools stay opt-in through an environment variable (`BASIRA_EVAL_NETWORK`, `BASIRA_REAL_ADAPTERS`) and are never silently skipped in CI: the CI job sets them.
