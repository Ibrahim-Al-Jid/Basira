# قبول بصيرة 2.3

التقييم وقبول آخر نسخة محلية موثّقين في هذا المستند. النتائج والأزمنة في هذا المستند تخص سجل القبول السابق، بما فيه تشغيل OpenRouter من المختبر القديم.

الإصدار المحلي يستخدم سجل `basira-static-3` بـ١١٤ فحصًا على سبعة مجالات (الكود المصدري أضافه P19). الواجهة بتفتح المختبر الموسّع افتراضيًا، والتوثيق التقني يعرض أسماء القواعد والمدخلات والأدوات. القاعدة بتتحسب ضمن المنطبق لما المحلل يقدر يفحصها فعليًا على المدخل والسياسة. [شروط الفحوصات](checks/README.md)

## الأدوار والأدوات والذاكرة

| الدور | المهام المسجلة |
|---|---|
| المايسترو (`orchestrator`) | التحقق من غلاف المدخل وحدوده، ثم توجيه نوع الملف لمحلل مسجّل. |
| الكشّاف (`planning`) | تطبيع الملفات أو اللقطة، وتثبيت سجل القواعد وسياسة المشروع. |
| الصيّاد (`analysis`) | تشغيل خصائص HTML، وسياسات المتصفح والاستجابات، والتبعيات، وإعدادات التشغيل، والمحللين الإضافيين. كل أداة تعرض القواعد المنطبقة والمطابقة والوقت وحالات التنفيذ. |
| المدقّق (`validation`) | مطابقة أعداد النتائج بالتغطية، والتحقق من إن كل نتيجة تخص قاعدة مسجّلة في خطة الفحص. |
| الكاتب (`reporting`) | تجهيز الملخص بالعربي والإنجليزي وتجميع التقرير. ترتيب OpenRouter اختياري، وبيتعامل مع معرّفات وأعداد محددة. |

أحداث التشغيل توضح تحقق كل دور، والتقرير يعرض ١٤ سجل مهمة في المسار الموسّع قبل الإثراء. تحويل التقرير القديم يفضل متوافق، ومعلومات المهمة اللي ما اتسجلتش وقتها تظهر كغير متاحة. ذاكرة النتائج تعرض حالة المراجعة مع أعداد المشاهدات. السجل بيحفظ الحالة الحالية والتعليقات والتغييرات وأسبابها. ترحيلات Alembic `0003` و`0004` تضيف جداول عزل المراجعة وتربط ملاحظات الإصدارات السابقة بالبصمات الجديدة. [نموذج البيانات](ERD.md)

## التقارير المتقدمة

- التقرير الحالي والتقرير المرجعي لازم يكونوا من نفس المشروع ونوع واسم المدخل وقيمة الهدف لو موجودة، ونفس نسخة السياسة والقواعد. التغطية المجمعة في حزم ZIP/JSON بتظهر اختفاء أو ظهور نتيجة كـ«تغيّر التغطية» عند غياب دليل على تنفيذ القاعدة لنفس الملف. لقطات HAR تحتاج معرّفات استجابات مستقرة قبل تمكين المقارنة.
- المحلّل ومدير المشروع يقدروا يضيفوا تعليقًا أو يغيّروا حالة نتيجة مع سبب. صلاحية Viewer تتيح القراءة، والـAPI وPostgreSQL بيعزلوا المراجعة حسب المشروع. حفظ حالة بشرية منفصل عن الاستنتاج اللي طالع من مقارنة الفحصين.

## التقييم

شغّل `python -m backend.synthetic_evaluation`. المجموعة الاصطناعية المستقلة فيها ١٨ حالة، و٢٥ قاعدة انطبقت مرة على الأقل. القياس يحسب تطابق أعداد النتائج لكل قاعدة وحالة. تقييم دقة مواضع النتائج وأداء المنصة على تطبيقات مختلفة يحتاج مجموعة أكبر بأدلة مرجعية لكل موضع.

| المجال | مطابق متوقع | زائد | فائت |
|---|---:|---:|---:|
| HTML | ٥ | ٠ | ٠ |
| المتصفح والاستجابات | ٤ | ٠ | ٠ |
| التبعيات | ١ | ٠ | ٠ |
| البنية التحتية | ٢ | ٠ | ٠ |
| CI/CD | ٢ | ٠ | ٠ |
| إعدادات التطبيق | ٢ | ٠ | ٠ |

تصحيح (٢٧ نوفمبر ٢٠٢٦): الجدول القديم كان بيقول HTML مطابق ٥ وفائت ٠، لكن السكربت كان بيدّي مطابق ٤ وفائت ١: الحالة `two-insecure-assets` متوقع منها نتيجتين `http-script` وكانت بترجّع واحدة، لأن سكربتين على نفس السطر كانوا بيتدمجوا في نتيجة واحدة. اتصلّح في PR #28 (عدّ نتائج نفس الأداة على نفس السطر منفصلة). الأرقام بعد الإصلاح: ١٨ حالة، دقة واستدعاء ١٫٠ في كل مجال، وHTML مطابق ٥ وزائد ٠ وفائت ٠. مجال الكود المصدري ضمن المخرجات لكن مفيش حالات فيه في المجموعة الاصطناعية، فمقاييسه فاضية.

في تشغيل ٢٧ نوفمبر بعد الإصلاح على ٥٤ عينة زمنية محلية (الحالات الـ١٨ ثلاث مرات)، الوسيط كان ٠٫٤٠٤ ms وp95 كان ١٫٠٢٩ ms (الأرقام بتتغير من جهاز لجهاز ومن تشغيل لتشغيل). الأرقام تخص محرك التحليل للملفات الصغيرة، إعادة ترتيب النتائج برد بديل للمزوّد سابت كل الأدلة نفسها.

## قبول التشغيل المحلي

- نجح بناء Docker من صور الأساس وإعادة تثبيت تبعيات Python من حزم محلية متحقق من بصمتها بعد تعطل التنزيل المباشر من PyPI داخل Docker. نجح `pip check` واتعاد اختبار المتصفح على الصورة الناتجة.
- نجح `npm test` بـ١٥٧ اختبارًا و٨ حالات فرعية. Chromium أنشأ حسابًا محليًا من الواجهة، ورفع ملف HTML في مشروع، ورجع فتح التقرير بعد الخروج والدخول. PostgreSQL وRedis/Celery وعامل التحليل المعزول اشتغلوا مع ترحيل الحسابات `platform_password_0005`. مزوّد OIDC اختُبر بمزوّد اختبار موقّع، وتشغيله مع جهة خارجية يحتاج إعداداتها.
- اختبار المتصفح غطّى رفع ملفين متوافقين وإظهار نتيجة جديدة وأخرى اتصلحت، ورسالة عدم توافق بعد تعديل سياسة الفحص، وحفظ مراجعة وتغيير الحالة. التقرير اتعرض بالعربي والإنجليزي، واترفض وصول جلسة مجهولة.
- نجحت استعادة نسخة PostgreSQL على قاعدة قبول منفصلة. اتطابق إصدار المخطط ومعرّفات المشاريع والفحوصات، وعدد الحسابات وعناصر سجل المراجعة وسياسات RLS. قاعدة SQLite رجعت من نفس ملفها بعد نقل المختبر إلى Docker، مع تحقق سلامة الملف وحفظ التقارير الخمسة الموجودة.
- اختبار OpenRouter الحي من إعدادات المختبر جلب الموديلات وشغّل فحص HTML اصطناعي بموديل مجاني. التقرير رجع حالة إثراء `model` واستدعاء واحد، وفضل متاح بعد تحديث الصفحة وفي تصدير JSON. اختبار الإثراء الحي ده يخص المختبر. [خطوات تشغيل المنصة](PLATFORM.md)

## Release 1 checklist (P18)

Run on 27 November 2026 against main at commit 59906b0. Status is passed, failed or not run. Nothing here is claimed beyond its stated source. The sections above are the older Arabic acceptance record; where they say Docker was built, that was an earlier environment and is not re-verified here.

| # | Item | Status | Source or command |
|---|---|---|---|
| 1a | Backend suite, frontend build, replay test and quality gate | passed in CI | GitHub Actions run 46059883912 on main at 59906b0 (job runs `pytest backend` and `python -m backend.quality_gate --network`) |
| 1b | Test count | reported, not re-run here | The P22/P23 change reported 396 passed, 2 skipped and quality gate exit 0. A local Python 3.10 run is not faithful (3.13 required) and is not used as evidence |
| 1c | Browser suites (Playwright) | runs in CI, not re-run here | Five suites run on every pull request in the `Browser smoke and container acceptance` job: personal projects, account (invitations, access, credentials), workspace routing and report scope, password signup, sign-in and cross-account isolation, and source intake with linked evidence (#155). The personal-projects suite was also run locally on 27 Nov in Arabic and English. The source intake suite was not re-run here |
| 2a | Everything done is recorded in `docs/PLAN.md` | passed | Phase table and Current position reviewed against main |
| 2b | `docs/RELEASE.md` current | passed with caveat | This section added. The older Arabic acceptance record is historical |
| 2c | Numbers in thesis and QUALITY match the measured source | passed after fixes | DVWA row in `docs/QUALITY.md` now matches `tests/fixtures/quality-baseline.json` (recall 0.615, precision 0.533, 1 of 13 clean files flagged). "100 checks" remains only as the historical pre-P19 figure. Old test counts are marked as earlier runs |
| 2d | Naming consistent | passed after fixes | Leftover `sentinel` folder paths and "Phase 10" guide reference removed. Catalog has 114 rules and 7 tools (`catalog()`, ruleset `basira-static-3`) |
| 2e | Links resolve, no stray phase files | passed | `backend/test_docs.py` |
| 2f | One organized source | partly done | `docs/PLAN.md` is the only tracker. Merging the large Arabic ARCHITECTURE, PLATFORM and WORKSPACE files is not done and stays open |
| 3 | Docker image and Compose | verified in CI since 28 November 2026 | The `container` job in `.github/workflows/ci.yml` builds the image and starts it on every push to main and every pull request; the job fails unless the app answers `/api/product` within 60 seconds. Green on #89 and on main (`28ed998`). `tests/container_smoke.py` itself is still not run in that job |
| 4 | No secrets in repo or history | passed for the patterns checked | grep for GitHub tokens, OpenRouter keys, AWS key ids and private key headers on tracked files and git history found nothing. The P22 change reported gitleaks with 0 leaks in 58 commits |
| 5 | Release notes and known limits | passed | `CHANGELOG.md`, and the limits listed here: most browser suites not re-run, real model provider and S3 intake not exercised, DVWA scores are development scores, SARIF export is out of scope |
