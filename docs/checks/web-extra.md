# فحوصات HTML وHAR الإضافية

المجموعة دي بتفحص ملفات HTML ولقطات HAR اللي المستخدم قدّمها. كل نتيجة بتشير لسطر HTML أو رقم الاستجابة داخل HAR. الدليل يذكر نوع الإعداد فقط، ويحجب محتوى الكوكي وكلمة المرور وبيانات العناوين والرؤوس. حالة `not_applicable` تعني إن اللقطة أو سياسة المشروع ماوفّرتش المدخل الكافي. حالة `review_required` تعني إن المؤشر المرصود محتاج سياق تشغيل قبل الحكم على أثره.

## HTML · ١٠ قواعد

| ID | الدليل والانطباق | سياسة المشروع |
|---|---|---|
| HTML-11 | سكربت كلاسيكي أو CSS من أصل آخر، ببصمة SRI صحيحة شكليًا ومن غير `crossorigin`. سكربتات modules تستخدم CORS تلقائيًا. | `base_url` |
| HTML-12 | رابط خارجي أو area له `target="_blank"` و`rel=opener` صراحةً. `noopener` أو `noreferrer` تمنع المطابقة. | `base_url` |
| HTML-13 | iframe من نفس الأصل أو `srcdoc` يجمع `allow-same-origin` و`allow-scripts` داخل `sandbox`. | `base_url` |
| HTML-14 | مستند متوقع على HTTPS يصرّح بعنوان HTTP في `src` لعنصر img أو audio أو video، أو `poster` لعنصر video. الفحص يقرأ التصريح، وتصرّف المتصفح ممكن يكون ترقية الرابط أو حجبه. | `base_url` |
| HTML-15 | أول `base href` في رأس الصفحة ينقل حل الروابط النسبيّة إلى أصل غير مسموح به. | `base_url`، و`base_origins_allowlist` اختيارية |
| HTML-16 | رابط أو area نشط يعلن endpoint خارجي في `ping`، حسب سياسة الخصوصية. | `base_url` و`disallow_external_pings: true` |
| HTML-17 | حقل password له اسم ومرتبط بنموذج طريقة الإرسال الافتراضية فيه GET. الدليل يصف الطريقة المعلنة والنماذج المرتبطة فقط. | لا يلزم |
| HTML-18 | حقل password له `value` غير فاضية في المصدر. السطر ونوع الخاصية يكفوا للدليل. | لا يلزم |
| HTML-19 | تلميح `preconnect` أو `dns-prefetch` من خارج الأصل وقائمة السماح. | `base_url` و`restrict_connection_hints: true`، و`connection_hint_origins_allowlist` اختيارية |
| HTML-20 | iframe خارجي يعلن تفويض الكاميرا أو المايك أو الموقع لأصل الإطار. النتيجة بتوصف التفويض المعلن، ووصول الإطار الفعلي يعتمد على سياسة الصفحة والمتصفح وإذن المستخدم. | `base_url`، و`sensitive_frame_origins_allowlist` اختيارية |

## HAR · ١٥ قاعدة

| ID | الدليل والانطباق | سياسة المشروع |
|---|---|---|
| WEB-11 | كوكي جلسة معروفة بخصائص مُلتقَطة، و`SameSite` غايبة أو قيمتها غير معروفة. | `session_cookie_names` و`require_explicit_samesite: true` |
| WEB-12 | كوكي جلسة يفترض تقتصر على المضيف وتحتوي على قيمة في `Domain`. | `session_cookie_names` و`session_cookie_host_only: true` |
| WEB-13 | CORS بيقبل بيانات اعتماد ويعلن أصلًا صريحًا غير مصرح به. قيمة `*` مع بيانات اعتماد يرفضها المتصفح، وبتظهر كحالة سليمة ضمن القاعدة دي. | `cors_credential_origins` قائمة للأصول المسموح بها. القائمة الفارغة تمنع كل الأصول. |
| WEB-14 | نفس عنوان GET في لقطتين نهائيتين يطابق قيمة Origin مختلفة في كل لقطة، مع تصريح بالتخزين المشترك وغياب `Vary: Origin` أو `Vary: *`. | `har_headers_complete: true` |
| WEB-15 | مستند HTML على HTTPS يحتاج عزل أصول و`COOP` فيه قيمة غير `same-origin` أو غايبة في التقاط كامل. | `require_cross_origin_isolation: true` |
| WEB-16 | مستند HTML على HTTPS يحتاج عزل أصول و`COEP` فيه قيمة غير `require-corp` أو `credentialless` أو غايبة في التقاط كامل. | `require_cross_origin_isolation: true` |
| WEB-17 | استجابة نهائية لمسار محمي من غير `CORP` المقيدة لنفس الأصل، أو لنفس الموقع لو السياسة بتسمح. | `corp_paths`، و`corp_same_site_allowed` اختيارية |
| WEB-18 | `Permissions-Policy` يعلن قيمة wildcard للكاميرا أو المايك أو الموقع. | لا يلزم |
| WEB-19 | استجابة خروج ناجحة على HTTPS من غير توجيه `Clear-Site-Data` للمخزن المؤقت والكوكيز، أو wildcard. | `clear_site_data_logout_paths` و`har_headers_complete: true` |
| WEB-20 | تنزيل ناجح من مسار محدد للملفات غير الموثوقة بيرجع `Content-Disposition` من غير `attachment`. | `untrusted_download_paths` |
| WEB-21 | رأس `Server` أو `X-Powered-By` بعنوان منتج فيه رقم إصدار. | `redact_server_versions: true` |
| WEB-22 | `WWW-Authenticate` يعلن تحدي Basic على HTTP في اللقطة. | لا يلزم |
| WEB-23 | استجابة إعادة توجيه محفوظة من HTTPS لعنوان HTTP صالح للتحليل. | لا يلزم |
| WEB-24 | حد تسجيل خدمة Service Worker في الهيدر أو مجلد السكربت الافتراضي خارج نطاق مجلد المشروع المسموح. يدعم المجلدات المطلقة المنتهية بـ`/`. | `service_worker_scopes` كائن بيربط مسار السكربت بمجلد النطاق المسموح |
| WEB-25 | استجابة ناجحة من مسار JSON مفروض بترجع نوع محتوى غير `application/json` أو `application/*+json`. | `expected_json_paths` |

خيارات المسارات أسماء كاملة زي `/api/data`، من غير query. لو هتراجع أكتر من مضيف في نفس HAR، حدّد `managed_hosts`. لما الحقل يغيب و`base_url` متاح، الفحص يقتصر على مضيف الـbase. عيّن `har_headers_complete` بعد التحقق إن التصدير شمل رؤوس الاستجابة المطلوبة. لو الحقل غايب أو `false`، كل فحص محتاج غياب رأس يتسجل `skipped` بسببه (`har_headers_incomplete`، أو `response_content_unreadable` لو جسم الاستجابة مش مقروء) والفحص يطلع `partial` بدل `completed`، فمفيش نتيجة "سليم" مبنية على رؤوس مش متجمعة. فحوصات الغياب بتحتاج الحالة دي، والفحوصات اللي ليها قيمة صريحة تقدر تستخدم القيمة الملتقطة.

مراجع السلوك المطبّق. [HTML Links](https://html.spec.whatwg.org/multipage/links.html) · [HTML iframe](https://html.spec.whatwg.org/multipage/iframe-embed-object.html) · [Subresource Integrity](https://www.w3.org/TR/sri-2/) · [Fetch](https://fetch.spec.whatwg.org/) · [Permissions Policy](https://w3c.github.io/webappsec-permissions-policy/) · [Service Workers](https://w3c.github.io/ServiceWorker/) · [Clear Site Data](https://www.w3.org/TR/clear-site-data/) · [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111) · [RFC 7617](https://www.rfc-editor.org/rfc/rfc7617) · [RFC 6266](https://www.rfc-editor.org/rfc/rfc6266)
