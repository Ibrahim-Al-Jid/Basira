# تشغيل مشاريع بصيرة وفحص الملفات

## تفعيل المشاريع الشخصية

تفعيل المسار الشخصي قرار تشغيل بعد مراجعة نسخة البيانات. جهّز نافذة صيانة توقف الكتابة والـDispatcher والعامل، وانتظر نهاية الفحوصات الجارية. جمّد مرجع الكود وملف الإعداد وتحقق من عدم وجود وظائف معلقة. خذ نسخة PostgreSQL بصيغة `pg_dump -Fc`. احفظ النسخ وإعداداتها في مكان خاص. استعد PostgreSQL في قاعدة منفصلة وفارغة باستخدام `pg_restore --exit-on-error --single-transaction`، وقارن أعداد الحسابات والمشاريع والفحوصات ومعرّفات التقارير وبصمات محتواها، وتحقق من أدوار قاعدة البيانات. [PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) · [PostgreSQL pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html)

1. شغّل `alembic upgrade head` بحساب الترحيل على النسخة المستعادة أولًا. تحقق من تطبيق `platform_personal_0012` ومن أن كل مشروع ظاهر مرتبط بالمالك الذي اعتمدته الخريطة.
2. استخدم `python ops/review-project-ownership.py` مع `BASIRA_PLATFORM_MIGRATION_URL` لعرض الحالات الملتبسة. أمّن قرارًا إداريًا مستقلًا قبل استخدام `--project <id> --owner <user-id> --decision-ref <ref>`. قارن الحالات التي ينقصها مالك بقائمة المراجعة. لو حصلت كتابة بالنسخة القديمة بعد اللقطة، أعد التحقق قبل التفعيل.
3. تحقق من منع حساب مختلف وغياب سياق المعاملة من الوصول إلى تقرير. شغّل `python -m pytest -q backend`، وبناء الواجهة، و`python tests/browser_personal_projects.py` ضد نسخة محلية منفصلة عبر `BASIRA_QA_ORIGIN` (بدون قيمة افتراضية، وفي CI هو `http://127.0.0.1:8901`). يمكن اختيار Microsoft Edge عبر `BASIRA_BROWSER_CHANNEL=msedge`.
4. بعد قبول النسخة المستعادة، كرر الترحيل على قاعدة التشغيل وفعّل `BASIRA_PERSONAL_PROJECTS=1` في نفس النافذة لكل خدمات منصة التطبيق والعامل والـDispatcher. رابط الدخول يفتح المشاريع الشخصية. الترحيل يحافظ على التقارير المرتبطة بمشاريع. تأكد إن الوضع فعال من `GET /api/product`.

الرجوع التشغيلي يكون بإرجاع قيمة الإعداد إلى `0` وإعادة تشغيل الخدمات على الكود المتوافق مع المخطط الموسّع، مع إبقاء التقارير محفوظة. قبل الإتاحة مجددًا، راجع أي مشاريع أو صلاحيات تغيّرت أثناء هذه الفترة. الرجوع عن المخطط بعد بدء كتابة بيانات شخصية يتطلب خطة استعادة لنسخة سبق اختبارها وقرارًا بشأن التغييرات الأحدث، لأن الاسترجاع يعيد القاعدة لنقطة النسخة. ترحيل Alembic التراكمي يحمي المخطط السابق ويمنع `downgrade` لو ظهر ما يستلزم الاحتفاظ به. [استراتيجيات ترحيل البيانات في Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#data-migrations-general-techniques)

## تشغيل مدخلات الفحص

1. شغّل ترحيل PostgreSQL حتى `platform_personal_github_0014` وفعّل `BASIRA_PERSONAL_PROJECTS=1`. من تفاصيل المشروع افتح «فحص جديد»، واختار ZIP أو GitHub أو رابط موقع، ثم راجع النطاق ووافق عليه. تتوحّد المصادر في نفس حالة الفحص وسجل الأدلة، وتظل التقارير السابقة قابلة للفتح.
2. لاستخدام S3 أو MinIO جهّز bucket خاصة مخصصة للحجر بتشفير واحتفاظ حسب بيئتك، ومن غير وصول عام. طبّق [قاعدة دورة الحياة](../ops/intake-quarantine-lifecycle.json) على `quarantine/` لتنظيف البقايا بعد تعطل العملية. امنح حساب التطبيق `s3:PutObject` و`s3:GetObject` و`s3:DeleteObject` على البادئة فقط. اضبط `BASIRA_INTAKE_S3_BUCKET` و`BASIRA_INTAKE_S3_ENDPOINT` للـMinIO وأسرار الاعتماد الخاصة بالخدمة. اضبط `BASIRA_INTAKE_STORAGE_REQUIRED=1` لإرجاع خطأ قابل لإعادة المحاولة عند غياب التخزين. وضع التطوير يدعم حجرًا مؤقتًا محليًا. لا تشارك بيانات تشغيل MinIO بين الاستضافة والاختبار. [صلاحيات S3](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3.html) · [دورة حياة كائنات S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) · [MinIO](https://github.com/minio/minio/releases)
3. اربط GitHub App بقراءة `Contents` و`Metadata` فقط، وفعّل انتهاء صلاحية التوكنات واختار **Only select repositories** عند التثبيت. سجّل Callback مطابقًا لقيمة `BASIRA_GITHUB_CALLBACK_URL` واضبط `BASIRA_GITHUB_CLIENT_ID` و`BASIRA_GITHUB_CLIENT_SECRET` و`BASIRA_GITHUB_CREDENTIAL_KEY` بمفتاح Fernet مستقل محفوظ كسر خادمي. بعد التثبيت افتح «اتصال GitHub» من الإعدادات. اختبر مستودعين، واحد مصرح والثاني خارج الاختيار. عند انتهاء رمز المستخدم يلزم الربط من جديد. لا تُحفظ رموز التحديث. فعّل تنقيح سجل طلبات الـCallback في أي proxy خارجي. [إعداد Callback](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-user-authorization-callback-url) · [رموز المستخدم](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
4. لجمع أدلة الموقع في بيئة اختبار، وثّق موافقة مالك الموقع وحدد عنوان الصفحة ومرجع الموافقة. اضبط `BASIRA_APPROVED_WEBSITE_PAGES` كخريطة JSON من معرّف المشروع إلى قائمة عناوين HTTPS كاملة، مثال `{"project_id":["https://example.com/"]}`. اختار مسارًا عامًا ثابتًا من غير معاملات أو معرّفات أشخاص، وبلا تحويلات. أزل الصفحة من القائمة عند سحب التفويض. الإتاحة العامة تتطلب ضبط وتحقق سياسة منع الخروج إلى الشبكات الخاصة في الاستضافة نفسها.

لاختبار الرحلات، شغّل `python -m pytest -q backend/test_personal_intake.py backend/test_github_import.py`. اختبارات GitHub تستخدم مزودًا محاكى، وتشمل رفض مستودع خارج الإذن وتكرار callback. استخدم bucket اختبار منفصلة بتشغيل نفس المجموعة مع إعدادات S3 للتحقق من SHA-256 وتنظيف الحجر. مكوّن التحليل يستقبل المدخل المقبول من الطابور، وتظل حدود حجمه كما هي.

## تشغيل الأدوات ونقطة الاستئناف

1. شغّل الترحيل حتى `platform_checkpoints_0015` على نسخة مستعادة أولًا. في PostgreSQL ينشئ الترحيل دالة ومحفّز `basira_clear_analysis_checkpoint`؛ تحقق من وجودهما ومن أن تحديث الحالة إلى `completed/partial/failed/cancelled` يصفّر `analysis_checkpoint`. على SQLite يكفي العمود الجديد لأن منطق التطبيق يتولى التنظيف.
2. صورة `basira-platform:scanner-local` تُبنى من الهدف `scanner-npm`. فهرس npm مبني من أرشيف OSV مثبّت بتاريخ وبصمة ظاهرين في `Dockerfile`؛ لا تحدّث البيانات بتنزيل وقت التشغيل. بناء صورة جديدة بمصدر وبصمة معلومين ثم استبدال العامل بعد التحقق هو مسار التحديث الوحيد.
3. الوسيط يتحقق من إصدار Gitleaks وOSV-Scanner قبل كل تنفيذ ويرفض أي إصدار لا يطابق السجل. ظهور `adapter_output_limit` أو `database_unavailable` يعني تغطية جزئية أو خطأ أداة في التقرير، وليس نتيجة سليمة.
4. الإثراء بالوكلاء اختياري. إذا كان مفعّلًا، البوابة ترسل معرّفات وأعدادًا وأسماء أدوات مسموحة فقط؛ أي رد غير مطابق يُرفض كاملًا ويظهر التقرير الحتمي. تذكّر أن `BASIRA_GATEWAY_URL` و`BASIRA_GATEWAY_TOKEN` سرّان خادميان، ولا يُكتبان في السجلات أو التقارير.
5. للتحقق الموضعي شغّل `python -m pytest -q backend/test_source_adapters.py backend/test_agent_workflow.py backend/test_checkpoints.py backend/test_advisor.py backend/test_personal_intake.py` ثم `npm run build`. اختبارات الـcheckpoint تستخدم قواعد SQLite مؤقتة وتغطي انهيار العامل والـlease القديم وتعديل التقرير والإلغاء وانتهاء المصدر.

### تجربة GitHub على Windows

لو دي أول مرة على التثبيت المحلي، شغّل الأمر ده من جذر المشروع على Windows باستخدام بيئة Python الخاصة ببصيرة. لو بصيرة بيشتغل على منفذ مختلف، أضف `--port` ورقم المنفذ.

```powershell
.\.venv\Scripts\python.exe .\ops\configure-local-github.py
```

1. من الصفحة اللي هتفتح اختار **Create on GitHub**، وراجع التسجيل وأكّده في GitHub. الإعداد بيطلب تطبيق خاص بصلاحية قراءة **Contents** والـWebhooks مقفولة. بصيرة يستلم بيانات التطبيق تلقائيًا ويحفظ إعداداته في مجلد `data` المحلي المتجاهَل في Git. [GitHub App Manifest](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest)
2. اضغط **Install on selected repositories**، واختار **Only select repositories** وحدد المستودع المطلوب. ارجع إلى [اتصال GitHub في بصيرة](http://127.0.0.1:8765/settings?tab=github)، واضغط **اربط GitHub** وأكّد التفويض. هتظهر المستودعات تلقائيًا بعد الرجوع. زر **حدّث المستودعات** يعيد تحميل القائمة لو غيّرت اختيارك على GitHub.
3. افتح مشروعك في بصيرة، ومن «فحص جديد» اختار GitHub والمستودع والفرع. بعد صدور التقرير تحقق من المستودع وCommit SHA وبصمة ZIP في «مصدر الفحص». لإغلاق القبول الخارجي، تحقق إن مستودعًا ثانيًا تقدر تشوفه على GitHub وخارج التثبيت مابيظهرش في بصيرة.

لو عندك GitHub App موجود، استخدم نفس الأمر مع `--manual` واحفظ بياناته من الطرفية. لو الإعداد مش ظاهر بعد الحفظ، أعد تحميل صفحة الاتصال وتأكد إنك فاتح عنوان `127.0.0.1` والمنفذ المسجّل في الـCallback. التهيئة من manifest تشتغل على نفس الجهاز اللي فيه مجلد البيانات. للتشغيل المستضاف، المشغّل يضبط بيانات التطبيق على الخادم، والمستخدم يكتفي بخطوة التفويض. [عنوان الرجوع في GitHub](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-user-authorization-callback-url)

### تطبيق بصيرة المشترك

مشغّل بيئة التطوير يجهّز GitHub App واحدًا ويحفظ بياناته في الخادم المحلي. يمكن تمرير المعرّفات العلنية باستخدام `--manual --client-id <client-id> --slug <app-slug>`، ويظل إدخال السر مخفيًا في الطرفية. يبدأ اختبار التطوير بمالك التطبيق ومستودع يختاره، وبعد الإعداد يستخدم كل حساب بصيرة زر «اربط GitHub» بتفويضه الخاص.

عند النشر، أضف عنوان HTTPS النهائي إلى نفس GitHub App كمطابقة حرفية، واضبطه في `BASIRA_GITHUB_CALLBACK_URL` مع بيانات التطبيق من مخزن أسرار السيرفر. لو مطلوب التثبيت على حسابات GitHub خارج حساب المالك، فعّل إمكانية التثبيت العام وقت القبول الخارجي وتحقق بحسابين ومستودعين منفصلين. [إتاحة تثبيت GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/making-a-github-app-public-or-private)

جمع أدلة HTTPS يراجع حتى ثلاث صفحات محددة مسبقًا لنفس أصل الصفحة المختارة. كل عنوان لازم يكون موجودًا في إعداد المشروع، وبطلب GET واحد لكل صفحة وحد ٢٥٠٬٠٠٠ بايت للاستجابة. الروابط داخل الصفحات تُحسب كجزء من التغطية وتظل خارج قائمة العناوين المطلوبة.

## التشغيل التقليدي

صفحة `/dashboard` تعرض النشاط، و`/projects` للمؤسسات والمشاريع والسياسات والصلاحيات، و`/new-scan` لمراجعة الملف والنطاق قبل التشغيل. فحوصات المشاريع بتستخدم PostgreSQL وطابور Redis/Celery. [خريطة مساحة العمل](WORKSPACE.md)

## تشغيل بيئة المشاريع محليًا

**للاستخدام على جهاز واحد** افتح `/projects` واختار «إنشاء حساب» ثم سجّل بإيميلك وكلمة مرور خاصة ببصيرة من ١٢ حرف أو أكتر. سكربت التشغيل المحلي (`ops/start-local.*`) يكتب في `.env.local` أعلام الحسابات المحلية (`BASIRA_PERSONAL_PROJECTS` و`BASIRA_PASSWORD_AUTH_ENABLED` و`BASIRA_PASSWORD_SELF_SIGNUP` بقيمة `1`). بيانات حسابات المشاريع محفوظة في PostgreSQL، وكلمات المرور محفوظة ببصمة Argon2id، والجلسة بتنتهي بعد ٨ ساعات وحد محاولات الدخول محفوظ في القاعدة. الإيميل هنا اسم دخول. استخدم OIDC لبيئة فريق تحتاج تحقق بريد أو استعادة حساب.

على Windows، شغّل Docker Desktop ونفّذ من جذر الريبو:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\start-local.ps1
```

أول مرة السكربت بيولّد كلمات مرور عشوائية لقاعدة البيانات في `.env.local`، وبيشغّل PostgreSQL وRedis والترحيلات ونسخة التطبيق اللي فيها الحسابات. السكربت بيكتب `BASIRA_PERSONAL_PROJECTS=1` وأعلام الحسابات المحلية في `.env.local` لوحده في كل تشغيل. في التشغيل التالي بيستخدم نفس الملف. لو المنفذ 8765 مستخدم، اختار منفذًا مختلفًا في أول تشغيل بإضافة `-Port 8775`. لو ملف `.env.local` موجود، عدّل `BASIRA_PORT` فيه.

للتشغيل اليدوي، جهّز `.env.local` من `ops/platform.env.example` في جذر المشروع. حط كلمات مرور عشوائية مختلفة من حروف وأرقام في `BASIRA_DB_PASSWORD` و`BASIRA_DISPATCH_PASSWORD` و`BASIRA_MIGRATION_PASSWORD`. Git وDocker build بيستبعدوا الملف.

```powershell
docker compose -p basira-local -f compose.yaml --env-file .env.local up -d --build
```

لو صفحة الدخول بتقول «تسجيل الدخول للمشاريع غير متاح حاليًا»، تأكد إنك فتحت عنوان `127.0.0.1` اللي بيطبعه السكربت. أمر `npm start` لو اتشغّل لوحده بيفتح المختبر. لو المختبر شغال، وقّفه بـ`Ctrl+C` في نافذته قبل تشغيل نسخة المشاريع على نفس المنفذ. نسخة Compose الأساسية من غير الأعلام دي في `.env.local` بتسيب حسابات الإيميل مقفولة بالإعداد الافتراضي. للتأكد إن نسخة المشاريع فعّلت التسجيل، افتح `/api/platform/auth/options` على نفس العنوان. الحسابات المحلية بتظهر مع `"password":true` وإنشاء الحساب مع `"registration":true`.

إنشاء الحسابات محدود بـ١٢ حسابًا كل ١٥ دقيقة لكل عنوان شبكة. لو اختبارات المتصفح اتشغّلت كذا مرة ورا بعض، التسجيل بيرجع 429 «وصلت لحد محاولات الدخول» مع ترويسة `Retry-After`. استنى لنهاية النافذة أو باعد بين التشغيلات.

لو صفحة الدخول ظهرت لكن حساب الجهاز القديم اترفض، فكل تثبيت جديد له قاعدة PostgreSQL مستقلة. اعمل حسابًا على الجهاز الجديد. لو محتاج نفس الحسابات والمشاريع والتقارير، هتحتاج تنقل بيانات PostgreSQL من الجهاز القديم. [مرجع تخزين كلمات المرور من OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

### تسجيل الدخول بحساب المؤسسة

1. انسخ `ops/platform.env.example` إلى `.env`، وحط قيم عشوائية مختلفة لـ`BASIRA_DB_PASSWORD` و`BASIRA_DISPATCH_PASSWORD` و`BASIRA_MIGRATION_PASSWORD`. استخدم حروف وأرقام فقط لكلمات المرور دي لأنها جزء من رابط اتصال PostgreSQL. لو المختبر الحالي شغال على 8765، اختار 8775 مثلًا في `BASIRA_PORT`، وعدّل منفذ الـcallback بنفس القيمة.
2. في مزوّد الهوية بتاعك سجّل عميل OIDC يقدر يستخدم Authorization Code مع PKCE S256. سجّل عنوان callback المطابق حرفيًا، واملأ `BASIRA_OIDC_ISSUER` و`BASIRA_OIDC_CLIENT_ID` و`BASIRA_OIDC_CLIENT_SECRET`. حط سر عشوائي ٣٢ حرفًا على الأقل في `BASIRA_OIDC_STATE_SECRET`. الـHTTP للـloopback المحلي، واستخدم HTTPS في التشغيل المستضاف.
3. من جذر المستودع شغّل `docker compose up --build -d`. خدمة `migrate` بتشغّل Alembic قبل التطبيق والعامل. استخدم `docker compose ps -a` للتحقق، وافتح `http://127.0.0.1:<port>/projects`.
4. سجّل الدخول، وأنشئ مؤسسة ومشروع، وبعدها حدّد أنواع الملفات في سياسة المشروع. سلطات Owner وAdmin وAnalyst وViewer في [التصميم المعماري](ARCHITECTURE.md). المالك يشارك دعوة خاصة من إدارة وصول المشروع، والمستلم يقبلها من الحساب. Analyst وViewer يحتاجوا Grant صريح من قائمة أعضاء المؤسسة.

قاعدة المشاريع تستخدم اتصال التطبيق `basira_app` بدون superuser أو BYPASSRLS. ترحيل المخطط له عنوان اتصال منفصل. موزّع المهام يتصل بحساب `basira_dispatch` بصلاحيات على الـoutbox فقط. المكوّن اللي بيحلّل الملفات معزول بشبكة `none` وبيقرأ من مساحة وسيطة للطلبات والردود. عامل Celery عنده وصول لـRedis وPostgreSQL وبيتعامل مع معرفات المهام، ومحاولته لها مهلة Lease. [PostgreSQL Row Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) · [Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)

### إضافة إثراء OpenRouter

على Windows، شغّل `ops/start-local.ps1 -Model` مرة واحدة. السكريبت بيكتب الإعدادات الأربعة (`BASIRA_PROJECT_MODEL_ENABLED` و`BASIRA_GATEWAY_URL` و`BASIRA_GATEWAY_TOKEN` و`BASIRA_MODEL_DB_PASSWORD`) في `.env.local` بقيم عشوائية، وبيشغّل خدمة `model-gateway` (profile اسمه `model`). بعد كده أي تشغيل عادي للسكريبت بيشغّلها طالما `BASIRA_PROJECT_MODEL_ENABLED=1` موجود. لو صفحة «اتصال الموديل» قالت إن البوابة مش متظبطة، ده معناه إن الإعدادات دي أو الـprofile ناقصين. للتشغيل اليدوي: اضبط `BASIRA_PROJECT_MODEL_ENABLED=1` و`BASIRA_GATEWAY_URL=http://model-gateway:8001`. أنشئ `BASIRA_GATEWAY_TOKEN` و`BASIRA_MODEL_DB_PASSWORD` بقيمتين عشوائيتين مستقلتين. كلمة مرور قاعدة البيانات تقبل ٢٤ إلى ١٢٨ حرفًا أو رقمًا (ASCII).

```powershell
docker compose -p basira-local -f compose.yaml --env-file .env.local --profile model up -d --build
```

بعد التشغيل، المالك أو المدير يفتح «الحساب ← اتصال الموديل»، يختار المؤسسة ويدخل مفتاح OpenRouter ومعرّف الموديل، ثم يسمح للمشروع في نفس المكان. التخزين مشفر بمفتاح خاص ببوابة الموديل. تفاصيل النسخ الاحتياطي والإعداد المشغّل القديم في سجلات المشروع في git (الدليل القديم اتشال من المستودع).

## المدخلات وتغطية الفحص

| النوع | المدخل المدعوم |
|---|---|
| HTML | ملف `.html` أو `.htm` بترميز UTF-8. |
| Repository | ZIP محلي، يُقرأ من الذاكرة بدون فك إلى نظام الملفات. ١٠٠٠ عنصر، وسقف ٥٠ ميجابايت بعد الفك ومليون بايت للملف. المسارات الخارجة والروابط الرمزية والتشفير والأرشيف المتداخل تُرفض. |
| HAR | لقطة `.har` فيها `log.entries` وبحد أقصى ٢٠٠ استجابة. استخدم لقطة منقّحة من القيم السرية قبل الرفع، مع الحفاظ على رؤوس الأمان والسمات المطلوبة للقياس. فحوصات غياب الرؤوس تتطلب إثبات اكتمال اللقطة في السياسة. |
| OpenAPI | ملف `.json` من إصدار 3.0 أو 3.1، فيه `info` و`paths`. يحصر عمليات المسارات والمصادقة المعلنة والمراجع، والتحليل يقتصر على نفس الوثيقة. |
| Config | JSON فيه `files` من الاسم النسبي للنص بترميز UTF-8، ومعاه `advisories` اختيارية كسجلات OSV محلية. راجع [مصفوفة القواعد](checks/README.md) لعائلات الإعدادات المدعومة. |

الملف المرسل قبل الفك بحد أقصى ١٠ ميجابايت. التقرير يحافظ على تغطية القواعد المئة. لقطة المصدر أو الإعدادات ممكن تضيف نتائج من Gitleaks وOSV-Scanner حسب نوع الملف والمحوّل المفعّل. لو أداة فشلت، تظهر حالتها والنتائج اللي ثبتت من الأدوات اللي اشتغلت. بعض الحالات ذات السياق تُعرض كمطلوبة للمراجعة. عنوان الهدف في السياسة للربط وتفسير اللقطة. التحليل بياخد الملف اللي قدمته.

خيارات السياسة في واجهة المشاريع بتقبل JSON. أبرزها `har_headers_complete`، و`managed_hosts`، و`require_csp`، و`require_frame_protection`، و`session_cookie_names`، و`private_paths`، و`registry_allowlist`، و`application`، و`repository_complete`، و`snapshot_complete`، و`protected_branches`. اسمح باختبارات الغياب لما اللقطة تتضمن كل البيانات المطلوبة: من غير `har_headers_complete: true` الفحوصات اللي بتقيس غياب رأس بتتسجل `skipped` والفحص يبقى `partial`. فحوصات التبعيات تدعم npm package-lock v2/v3 وملفات OSV المقدمة، وTerraform المدعوم هو إعدادات JSON الثابتة.

## حالات التشغيل والذاكرة

- تقديم الفحص يرجع معرّف ورابط متابعة. الخادم يسجل المهمة وطلب التسليم في نفس المعاملة. الأحداث لها أرقام متزايدة، والواجهة تجيب الجديد بالمؤشر وتستعيد الحالة بعد تحديث الصفحة. الإلغاء يقفل المهمة ويمنع كتابة تقرير من محاولة متأخرة.
- PostgreSQL يخزن المهام والنسخ النهائية والأدلة ويزيل محتوى المدخل من صف الفحص عند الحالة النهائية. مساحة التحليل المؤقتة تُنظّف عند انتهاء الطلب. حافظ على تشفير ومدة احتفاظ لنسخ قاعدة البيانات في بيئتك، خصوصًا لأن المدخل موجود في قاعدة المهام أثناء التشغيل.
- ذاكرة العمل هي الحالة والأحداث، وEpisodic تاريخ الفحوصات، وProcedural سجل القواعد، وProject نسخة السياسة، وFinding تكرار الأدلة على مستوى القاعدة والملف، وSemantic مراجع يضيفها مدير المشروع ويقدر يبطلها. واجهة الذاكرة تعزلها بالمؤسسة والمشروع. سياق المحتوى الخام والمراجع الحرة لا يدخل استدعاء النموذج.

للتحقق على مشروع Compose معزول بقاعدة اختبار، شغّل `Get-Content -Raw tests/container_smoke.py | docker compose exec -T app python -` من PowerShell. الاختبار يضيف حسابين مؤقتين في القاعدة، ويتحقق من RLS ومسار الـworker والتقرير. اختبارات OIDC في `npm test` تستخدم مزوّد اختبار لتجربة التوقيع وPKCE وحالات الرفض.

في تقرير المشروع، اختار المرجع من قسم «مقارنة الفحوصات». حالة النتيجة والتعليقات تحت «مراجعة النتائج». الترحيل `platform_observation_0004` يُنفَّذ على قاعدة فعلية باستخدام `alembic upgrade head` بحساب الترحيل. ده بيحدّث بصمات البيانات الموجودة جوّه معاملة الترحيل. [التقارير المتقدمة وحدود المقارنة](RELEASE.md)
