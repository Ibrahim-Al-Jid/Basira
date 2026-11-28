// Dashboard helpers (P10 slice e): pure functions, no React, no network.
export const BAR_MAX_PERCENT = 100;

// Bar height in percent for each scan, scaled to the largest count; a scan with findings never rounds to zero.
export function barHeights(scans) {
  const max = Math.max(0, ...scans.map((scan) => scan.findings));
  return scans.map((scan) => (max === 0 ? 0 : scan.findings === 0 ? 0 : Math.max(4, Math.round((scan.findings / max) * BAR_MAX_PERCENT))));
}

const REASONS = {
  coverage_unavailable: ["مفيش تغطية كافية للمقارنة", "Not enough coverage to compare"],
  incompatible_scope: ["الفحص السابق على مدخل مختلف", "The earlier scan used a different input"],
  incompatible_policy: ["سياسة المشروع اتغيرت بين الفحصين", "The project policy changed between the scans"],
  incompatible_ruleset: ["إصدار القواعد اتغير بين الفحصين", "The ruleset version changed between the scans"],
};

// What to show for the change against the previous scan: counts when comparable, a reason when not.
export function changeView(change) {
  if (!change) return { kind: "first" };
  if (!change.comparable) return { kind: "incomparable", reason: REASONS[change.reason] || ["مش قابلة للمقارنة", "Not comparable"] };
  return { kind: "counts", new: change.new, resolved: change.resolved, unchanged: change.unchanged, coverageChanged: change.coverage_changed };
}

export function coverageText(coverage) {
  return coverage ? { ran: coverage.ran, total: coverage.total } : null;
}
