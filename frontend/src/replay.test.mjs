import assert from "node:assert/strict";
import test from "node:test";
import { MAX_GAP_MS, MIN_GAP_MS, canReplay, gapAfter, replayDelays, replayTotalMs } from "./replay.js";

const at = (seconds) => ({ occurred_at: new Date(Date.UTC(2026, 10, 27, 12, 0, seconds)).toISOString() });

test("gaps are clamped between the minimum and maximum", () => {
  assert.equal(gapAfter(at(0), at(0)), MIN_GAP_MS);
  assert.equal(gapAfter(at(0), at(1)), 1000);
  assert.equal(gapAfter(at(0), at(600)), MAX_GAP_MS);
});

test("speed shortens the delays and never reaches zero", () => {
  assert.equal(gapAfter(at(0), at(1), 2), 500);
  assert.ok(gapAfter(at(0), at(0), 4) > 0);
  assert.ok(replayTotalMs([at(0), at(1), at(2)], 4) < replayTotalMs([at(0), at(1), at(2)], 1));
});

test("bad or backwards timestamps fall back to the minimum gap", () => {
  assert.equal(gapAfter({ occurred_at: "x" }, at(1)), MIN_GAP_MS);
  assert.equal(gapAfter(at(5), at(1)), MIN_GAP_MS);
});

test("one delay per event, first event after one beat", () => {
  const delays = replayDelays([at(0), at(2), at(3)]);
  assert.equal(delays.length, 3);
  assert.equal(delays[0], MIN_GAP_MS);
  assert.deepEqual(replayDelays([]), []);
});

test("only finished scans with events can be replayed", () => {
  assert.equal(canReplay({ state: "completed" }, [at(0)]), true);
  assert.equal(canReplay({ state: "partial" }, [at(0)]), true);
  assert.equal(canReplay({ state: "running" }, [at(0)]), false);
  assert.equal(canReplay({ state: "completed" }, []), false);
  assert.equal(canReplay(null, [at(0)]), false);
});
