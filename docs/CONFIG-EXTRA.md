# فحوصات إعدادات إضافية

الـ٢٥ فحص دول بيحللوا الملفات النصية اللي المستخدم قدّمها في لقطة مستودع أو إعدادات. الفحص بيقرأ القيم الثابتة محليًا، ويعرض اسم الملف ورقم السطر ودليل منقّح وإصلاح بالعربي والإنجليزي. مطابقة إعداد محفوظ بتوصف اللي مكتوب في اللقطة، وإعدادات التشغيل الفعلية تحتاج إثبات منفصل. الدليل بيحجب بيانات اعتماد npm ونص إشعار إيقاف دعم الحزمة.

## تبعيات npm

| المعرّف | المدخل والانطباق | دليل النتيجة |
|---|---|---|
| DEP-09 | ملف `.npmrc` فيه إعداد `strict-ssl` صريح. | القيمة الفعالة في الملف بتعطّل التحقق من شهادة السجل. |
| DEP-10 | عنوان HTTP أو HTTPS لحزمة خارجية في قفل npm v2/v3. | العنوان فيه بيانات اعتماد حرفية. العنوان وقيم الاعتماد محجوبة من الدليل. |
| DEP-11 | حقل اعتماد معروف في `.npmrc`. | قيمة حرفية لحقل `_auth` أو `_authToken` أو `_password`. |
| DEP-12 | تبعية إنتاج مباشرة أو اختيارية معرّفة في `package.json`. | محدد إصدار غير مقيّد، مثل الإصدار العام أو وسم `latest`. |
| DEP-13 | سياسة `npm_require_private_package: true` وحقل نشر صريح. | `publishConfig.access` يسمح بالنشر العام والحزمة مش موسومة كخاصة. |
| DEP-14 | لقطة عليها `repository_complete: true` وتبعية محلية `file:` أو `link:`. | المرجع يخرج عن جذر اللقطة المقدّمة بعد تطبيع المسار. |
| DEP-15 | حزمة من سجل مع بصمة سليمة شكليًا في ملف القفل. | القفل بيسجل SHA‑1 فقط، من غير بصمة أقوى صالحة شكليًا. |
| DEP-16 | تبعية مباشرة من سجل مثبتة في قفل v2/v3. | القفل يحتوي على علامة إيقاف دعم للإصدار المثبت. النتيجة مؤشر لمراجعة الصيانة. |

فحص القفل يقرأ مسارات الحزم وتعريف الجذر، ويدي الأولوية لـ`npm-shrinkwrap.json` لو الملفين موجودين. [npmrc](https://docs.npmjs.com/cli/v11/configuring-npm/npmrc/) · [package-lock.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/) · [package.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/)

## Kubernetes

| المعرّف | المدخل والانطباق | دليل النتيجة |
|---|---|---|
| INF-11 | Pod أو workload مدعوم في YAML/JSON. | `hostIPC` مفعّل صراحةً. |
| INF-12 | `hostPort` رقمي معروف في تصريح حاوية. | المنفذ موجب وخارج `kubernetes_allowed_host_ports`. غياب القائمة يعني إن مفيش منفذ معتمد. |
| INF-13 | `procMount` صريح بقيمة معروفة. | `procMount` يطلب `Unmasked`. |
| INF-14 | إعداد seccomp مكتوب للحاوية أو موروث من الـPod. | إعداد الحاوية الفعلي في الملف هو `Unconfined`. |
| INF-15 | سياسة `kubernetes_require_read_only_root: true` وإعداد صريح للحاوية. | `readOnlyRootFilesystem` معطّل. |
| INF-16 | `runAsUser` رقمي للحاوية أو موروث من الـPod. | UID يساوي صفر، وإعداد `runAsNonRoot` مش مفعّل في نفس التكوين. |
| INF-17 | سياسة `kubernetes_forbid_service_account_token: true` وإعداد تركيب صريح للـPod. | `automountServiceAccountToken` مفعّل صراحةً. |
| INF-18 | قائمة `kubernetes_forbidden_sysctls` فيها قيم محظورة. | أحد إعدادات `spec.securityContext.sysctls` يطابق القائمة. الفاصلين `/` و`.` يتوحّدوا عند المقارنة. |

بيتحلل إعداد الـPod والحاويات الأساسية والمؤقتة و`initContainers` في الموارد المدعومة. القاعدة اللي تعتمد على إعداد موروث بتراعي قيمة الحاوية لو موجودة. [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) · [إعداد حسابات الخدمة للـPods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)

## GitHub Actions

| المعرّف | المدخل والانطباق | دليل النتيجة |
|---|---|---|
| CI-07 | مهمة reusable workflow وسياسة `ci_forbid_secret_inheritance: true`. | المهمة تضبط `secrets: inherit`. |
| CI-08 | ملف workflow يُشغّل عند حدث طلب دمج وله مهمة على runner صريح. | المهمة بتستخدم وسم `self-hosted`. الدليل مؤشر لمراجعة مصدر الكود وحدود الثقة. |
| CI-09 | مهمة تشغيل وسياسة `ci_max_job_timeout_minutes`. | المهلة الصريحة أو الافتراضية تتجاوز السياسة. قيمة تعتمد على تعبير تُترك خارج الانطباق للحالة دي. |
| CI-10 | مهمة اسمها موجود في `ci_required_jobs`. | `continue-on-error` مفعّل صراحةً على المهمة المطلوبة. |

السياسات المرتبطة بالمهمة تستخدم معرّفات jobs من ملف workflow. [صياغة GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) · [إرشادات استخدام Actions بأمان](https://docs.github.com/en/actions/reference/security/secure-use)

## إعدادات التطبيق

| المعرّف | المدخل والانطباق | دليل النتيجة |
|---|---|---|
| APP-07 | إعداد بيئة Node معروف بقيمة نصية أو رقمية صريحة. | `NODE_TLS_REJECT_UNAUTHORIZED` مضبوط على صفر. |
| APP-08 | حقل HttpOnly لكوكي الجلسة في إعدادات إطار عمل مدعومة. | الإعداد يعطّل HttpOnly صراحةً. |
| APP-09 | `ALLOWED_HOSTS` قائمة أو tuple حرفية في إعدادات Python. | القائمة فيها wildcard يسمح بكل أسماء المضيفين. |
| APP-10 | تصريح CORS ثابت فيه اختيار سياسة الأصول وبيانات الاعتماد. | السماح بكل الأصول ومرور بيانات الاعتماد مفعّلين معًا. |
| APP-11 | مفتاح `WTF_CSRF_ENABLED` معروف بقيمة صريحة. | الإعداد يعطّل حماية CSRF لـFlask‑WTF. |

إعدادات التطبيق بتُقرأ من ملفات Python الثابتة وملفات البيئة وProperties وINI وYAML/JSON المدعومة. مسارات `fixtures` والأنماط المعلنة في `fixture_paths` مستبعدة من قواعد التطبيق. [Node CLI](https://nodejs.org/api/cli.html#node_tls_reject_unauthorizedvalue) · [إعدادات Django](https://docs.djangoproject.com/en/stable/ref/settings/) · [django-cors-headers](https://github.com/adamchainz/django-cors-headers) · [إعدادات Flask-WTF](https://flask-wtf.readthedocs.io/en/stable/config/)
