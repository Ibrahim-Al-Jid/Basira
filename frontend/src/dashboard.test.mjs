import assert from "node:assert/strict";
import test from "node:test";
import { barHeights, changeView, coverageText } from "./dashboard.js";

test("bars scale to the largest scan and keep small counts visible", () => {
  assert.deepEqual(barHeights([{ findings: 10 }, { findings: 5 }, { findings: 0 }, { findings: 1 }]), [100, 50, 0, 10]);
  assert.deepEqual(barHeights([{ findings: 1000 }, { findings: 1 }]), [100, 4]);
  assert.deepEqual(barHeights([{ findings: 0 }, { findings: 0 }]), [0, 0]);
  assert.deepEqual(barHeights([]), []);
});

test("change view separates first scan, counts and incomparable scans", () => {
  assert.equal(changeView(null).kind, "first");
  const counts = changeView({ comparable: true, new: 2, resolved: 3, unchanged: 4, coverage_changed: 1 });
  assert.deepEqual(counts, { kind: "counts", new: 2, resolved: 3, unchanged: 4, coverageChanged: 1 });
  const bad = changeView({ comparable: false, reason: "incompatible_scope" });
  assert.equal(bad.kind, "incomparable");
  assert.match(bad.reason[1], /different input/);
  assert.equal(changeView({ comparable: false, reason: "other" }).reason[1], "Not comparable");
});

test("coverage text is null when the scan has no coverage", () => {
  assert.equal(coverageText(null), null);
  assert.deepEqual(coverageText({ ran: 8, total: 114 }), { ran: 8, total: 114 });
});
