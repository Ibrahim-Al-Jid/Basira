export const agents = {
  orchestrator: [
    "المايسترو",
    "Maestro",
    "نطاق المراجعة وملخص الذاكرة",
    "يحدّد مسار التشغيل ويوجّه العمل للكشّاف.",
    "قرار التنسيق",
    "LangGraph",
  ],
  planning: [
    "الكشّاف",
    "Scout",
    "تعليمات المايسترو والقواعد المتاحة",
    "يوزّع المراجعة على فروع التحليل المناسبة.",
    "خطة فحص محددة",
    "كتالوج القواعد",
  ],
  analysis: [
    "الصيّاد",
    "Hunter",
    "الخطة ونتائج فحص التصريحات",
    "يراجع نتائج الفحص المحلي حسب الفرع المكلّف به.",
    "معرّفات القواعد المطابقة للفرع",
    "فاحص HTML المحلي",
  ],
  validation: [
    "المدقّق",
    "Auditor",
    "أدلة محلّل HTML ونتائج الفروع",
    "يثبت كل موضع مطابق بقاعدة ودليل محلي.",
    "ملاحظات موثّقة",
    "مطابقة الأدلة",
  ],
  reporting: [
    "الكاتب",
    "Scribe",
    "الملاحظات والقياسات النهائية",
    "يلخّص الملاحظات وأولويات الإصلاح باللغتين.",
    "تقرير عربي وإنجليزي",
    "مُنشئ التقارير",
  ],
};
export const num = (value) => new Intl.NumberFormat("ar-EG").format(value);
export const dateText = (value) =>
  new Date(value).toLocaleString("ar-EG", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
export async function fetchJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw Error("تعذّر الاتصال بالخادم. اتأكد من الإنترنت وحاول تاني.");
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw Error("الخدمة غير متاحة حاليًا. حاول مرة تانية.");
  }
  if (!response.ok)
    throw Error(
      typeof body.detail === "string" && /[\u0600-\u06ff]/.test(body.detail) ? body.detail : "تعذّر تنفيذ الطلب.",
    );
  return body;
}
export const post = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
