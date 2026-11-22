# وثائق مرحلة 14

## جدول القبول

| الطلب | implemented | evidence | accepted | remaining |
|-------|-------------|----------|----------|-----------|
| 14.1 — عقد إدخال ومخرجات موحّد | نعم | contracts.py (18-245), artifact_review.py (324), platform_runtime.py (305), test_website_intake_exact_approval_and_passive_report (332-364) | مقبول | لا |
| 14.2 — ZIP وحفظ اللقطة | نعم | artifact_review.py (118-172), test_personal_intake.py (110-157), offline_worker.py (24) | مقبول | لا |
| 14.3 — اتصال GitHub واختيار المستودع | نعم | personal_github.py, github_import.py, test_personal_github_oauth_rechecks_selected_repo_and_pins_commit (159-265) | مقبول | لا |
| 14.4 — جمع أدلة الموقع المصرّح به | نعم | intake_website.py (37-224), zap_passive.py (40-81), artifact_review.py (412-434), test_website_intake_exact_approval_and_passive_report (332-364), test_website_rejects_nonpublic_dns_and_redirect (366-381), test_website_capture_uses_pinned_socket_with_verified_tls (384-435), test_website_capture_is_limited_to_three_approved_pages_on_same_origin (437-455) | مقبول | لا |
| 14.5 — توحيد تجربة بدء الفحص | نعم | phase9_contracts.py (13-17), contracts.py (216-244), test_personal_intake.py (73-157, 159-265, 332-364) | مقبول | لا |

## تحقق إضافي من الشكاوى الأمنية · ٢٢ نوفمبر ٢٠٢٦

- **TLS:** `HTTPSConnection` يُنشأ باسم المضيف المعتمد وسياق التحقق الافتراضي، ثم يُمرَّر العنوان المُتحقَّق منه إلى `_create_connection`. حين يلتف المقبس يستخدم `server_hostname` اسم المضيف لا العنوان، لذلك يظل التحقق من الشهادة وSNI مرتبطين بالنطاق المعتمد. الاختبار `test_website_capture_uses_pinned_socket_with_verified_tls` يثبت وصول الاتصال إلى العنوان المثبّت مع ترويسة `Host: example.test`، ويرفض شهادة نطاق مختلف.
- **إعادة حل DNS:** `validated_address` تُستدعى قبل الاتصال، ويُثبَّت ناتجها في المقبس؛ لا يوجد حل ثانٍ وقت الاتصال، وكل صفحة إضافية تُعاد لها العملية. عناوين البيانات الوصفية السحابية تقع ضمن النطاقات غير العامة التي يرفضها الفحص.
- **إبطال GitHub:** `DELETE /applications/{client_id}/token` هو نقطة النهاية الموثّقة لإبطال رمز مستخدم GitHub App (`ghu_*`) عند توثيق التطبيق بـBasic. أُضيف تأكيد على مسار الطلب وجمع الرمز في الاختبار.
- **نطاق التثبيت:** `available_installations` يقبل فقط التثبيتات غير المعلّقة ذات `repository_selection: selected` وصلاحيات `contents` و`metadata` للقراءة فقط. أُضيف اختبار مستقل يرفض `all` والتعليق و`contents: write` والصلاحيات الإضافية.
- لم يتوفر daemon الخاص بـDocker محليًا، لذا لم يُبنَ `scanner-npm`؛ هذا تحفّظ تشغيل مسجّل وليس فجوة في الكود.