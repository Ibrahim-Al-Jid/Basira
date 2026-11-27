from . import dashboard, platform_jobs as jobs
from .test_platform_runtime import artifact, platform, submit  # noqa: F401


def run(owner, ctx, content, key):
    scan = submit(owner, ctx, artifact(name="site.html", content=content), key=key).json()["id"]
    jobs.execute_scan(ctx.org_id, ctx.project_id, scan)
    return scan


def test_dashboard_numbers_reconcile_with_each_scan(platform):  # noqa: F811
    owner, stranger, ctx = platform
    root = f"/api/platform/projects/{ctx.project_id}"
    empty = owner.get(root + "/dashboard").json()
    assert empty["scans"] == [] and empty["latest"] is None and empty["as_of"].endswith("Z")
    first = run(owner, ctx, b'<script src="http://assets.test/main.js"></script>', "dash-key-1")
    second = run(owner, ctx, b"<p>clean page</p>", "dash-key-2")
    view = owner.get(root + "/dashboard").json()
    assert [item["scan_id"] for item in view["scans"]] == [first, second]
    assert view["latest"]["scan_id"] == second
    for item in view["scans"]:
        report = owner.get(f"{root}/reports/{item['scan_id']}").json()
        assert item["findings"] == len(report["findings"])
        assert item["unique_findings"] == len({finding["rule"] for finding in report["findings"]})
        assert sum(item["severity"].values()) == item["findings"]
        assert item["created_at"] == report["created_at"]
        assert item["coverage"]["total"] == len(report["coverage"]) == 114
    assert view["scans"][0]["findings"] > 0 and view["scans"][1]["findings"] == 0
    assert view["scans"][0]["change"] is None
    change = view["scans"][1]["change"]
    assert change["baseline_scan_id"] == first and change["comparable"], change
    direct = owner.get(f"{root}/reports/{second}/compare", params={"baseline": first}).json()
    for kind in ("new", "resolved", "unchanged", "coverage_changed"):
        assert change[kind] == sum(1 for row in direct["changes"] if row["change"] == kind), kind
    assert sum(change[kind] for kind in ("new", "resolved", "unchanged", "coverage_changed")) == len(direct["changes"]) >= 1
    assert stranger.get(root + "/dashboard").status_code == 404


def test_build_keeps_the_newest_scans_only_and_oldest_first():
    class Fake:
        def __init__(self, number):
            self.id, self.created_at, self.status = f"s{number}", f"2026-11-{number:02d}T00:00:00Z", "completed"
            self.findings, self.coverage, self.input_artifact = [], None, None

    entries = [(Fake(number), {}) for number in range(20, 0, -1)]
    view = dashboard.build(entries, now=None)
    assert len(view["scans"]) == dashboard.SCAN_LIMIT
    assert view["scans"][-1]["scan_id"] == "s20" and view["scans"][0]["scan_id"] == "s9"
    assert view["scans"][0]["change"] is None and view["scans"][0]["coverage"] is None
