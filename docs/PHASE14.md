# وثائق مرحلة 14

## جدول القبول

| الطلب | implemented | evidence | accepted | remaining |
|-------|-------------|----------|----------|-----------|
| 14.1 — عقد إدخال ومخرجات موحّد | نعم | contracts.py (18-245), artifact_review.py (324), platform_runtime.py (305), test_website_intake_exact_approval_and_passive_report (332-364) | مقبول | لا |
| 14.2 — ZIP وحفظ اللقطة | نعم | artifact_review.py (118-172), test_personal_intake.py (110-157), offline_worker.py (24) | مقبول | لا |
| 14.3 — اتصال GitHub واختيار المستودع | نعم | personal_github.py, github_import.py, test_personal_github_oauth_rechecks_selected_repo_and_pins_commit (159-265) | مقبول | لا |
| 14.4 — جمع أدلة الموقع المصرّح به | نعم | intake_website.py (37-224), zap_passive.py (40-81), artifact_review.py (412-434), test_website_intake_exact_approval_and_passive_report (332-364), test_website_rejects_nonpublic_dns_and_redirect (366-381), test_website_capture_uses_pinned_socket_with_verified_tls (384-435), test_website_capture_is_limited_to_three_approved_pages_on_same_origin (437-455) | مقبول | لا |
| 14.5 — توحيد تجربة بدء الفحص | نعم | phase9_contracts.py (13-17), contracts.py (216-244), test_personal_intake.py (73-157, 159-265, 332-364) | مقبول | لا |