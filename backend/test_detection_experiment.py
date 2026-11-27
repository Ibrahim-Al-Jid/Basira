from .detection_experiment import load_manifest, score


def test_manifest_labels_use_real_taxonomy_subdomains_and_pair_each_file_with_a_clean_version():
    from .taxonomy import subdomains
    known = {item["id"] for _, item in subdomains()}
    manifest = load_manifest()
    vulnerable = [case for case in manifest["cases"] if case["vulnerable"]]
    assert vulnerable and all(case["subdomain"] in known for case in vulnerable)
    assert len(vulnerable) == len(manifest["cases"]) - len(vulnerable)


def test_score_counts_hits_and_flagged_clean_files():
    manifest = load_manifest()
    vulnerable = next(case for case in manifest["cases"] if case["vulnerable"])
    clean = next(case for case in manifest["cases"] if not case["vulnerable"])
    result = score(manifest, {vulnerable["path"]: {vulnerable["subdomain"]}, clean["path"]: {"D08.1"}})
    assert result["found"] == 1 and result["clean_files_flagged"] == 1
    assert score(manifest, {})["detection_rate"] == 0
