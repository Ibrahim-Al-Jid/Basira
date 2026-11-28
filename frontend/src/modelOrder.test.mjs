import assert from "node:assert/strict";
import test from "node:test";
import { modelOrderNote, suggestedPriority } from "./modelOrder.js";

test("a model-enriched report with a priority list gets the note in both languages", () => {
  const priority = suggestedPriority({ enrichment: "model", priority: ["rule.a", "rule.b"] });
  assert.deepEqual(priority, ["rule.a", "rule.b"]);
  assert.equal(modelOrderNote(priority, "en"), "Order suggested by the model");
  assert.equal(modelOrderNote(priority, "ar"), "ترتيب الأولويات المقترح من الموديل");
});

test("no note when the order is not model-suggested", () => {
  for (const report of [
    { enrichment: "rules", priority: ["rule.a"] },
    { priority: ["rule.a"] },
    { enrichment: "model" },
    { enrichment: "model", priority: "rule.a" },
    null,
  ]) {
    const priority = suggestedPriority(report);
    assert.equal(priority, null);
    assert.equal(modelOrderNote(priority, "en"), null);
    assert.equal(modelOrderNote(priority, "ar"), null);
  }
});

test("an empty priority list gives no note", () => {
  assert.equal(modelOrderNote(suggestedPriority({ enrichment: "model", priority: [] }), "en"), null);
});
