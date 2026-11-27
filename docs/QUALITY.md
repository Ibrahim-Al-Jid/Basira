# Quality gates

Detection rate alone rewards noisy checks. Every measured set records three numbers, and a change fails when recall or precision drops or the false-positive rate rises. Plan item: P23 in [PLAN.md](PLAN.md).

## What is measured

| Set | Input | Needs network | Baseline (27 Nov 2026) |
|---|---|---|---|
| `reference_corpus` | 12-case regression corpus, static adapters, mocked profile | no | precision 0.900, recall 0.900 (9 true, 1 false, 1 missed) |
| `dvwa_static` | 13 vulnerable and 13 fixed DVWA files at a pinned commit, static checks only | yes | recall 0.000 (0 of 13), precision undefined (no findings), false-positive rate 0 of 13 clean files |

The reference corpus was written together with the checks, so it guards against regressions and proves little about detection. DVWA is the independent set; its labels come from one reader. The unit is a (file, taxonomy subdomain) pair. A pair reported anywhere other than a labeled vulnerability is a false positive, including the same subdomain on a fixed file. The false-positive rate is fixed files flagged divided by fixed files. The mocked profile simulates the external adapters, so its numbers are not a claim about the real tools.

## Run it

```
python -m backend.quality_gate            # offline corpus, exit 1 on a regression
python -m backend.quality_gate --network  # also DVWA (downloads the pinned files, checks digests)
python -m backend.quality_gate --print    # print current numbers, compare nothing
pytest backend/test_quality_gate.py       # same gate through pytest; set BASIRA_EVAL_NETWORK=1 for DVWA
```

The baseline is `tests/fixtures/quality-baseline.json`. Improvements never fail. Raise the baseline in the same change that earns the improvement, with the printed numbers in the changelog line. Never lower it to make a change pass; a lower number needs the owner's decision recorded in the plan.

## Flaky tests

A test that fails and then passes with no code change is a defect, not noise.

1. Never re-run until green. Record the test name and the failure in the pull request that found it.
2. Fix it within the same pull request when the cause is clear (time, ordering, shared state, network).
3. If it cannot be fixed now, mark it `@pytest.mark.skip(reason="flaky: <cause>, owner: <name>, <date>")`, and add a line to the plan under the owning phase. A skip without a reason, owner and date is not accepted.
4. Tests that need the network or external tools stay opt-in through an environment variable (`BASIRA_EVAL_NETWORK`, `BASIRA_REAL_ADAPTERS`) and are never silently skipped in CI: the CI job sets them.
