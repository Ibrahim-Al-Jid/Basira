export const sample = `<!doctype html>
<html lang="en">
<head>
  <title>Demo storefront</title>
  <script src="http://assets.example.test/store.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/demo-store@1.0.0/index.js"></script>
</head>
<body>
  <form action="http://checkout.example.test/order" method="post">
    <button>Place order</button>
  </form>
</body>
</html>`;

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
export const roleOf = (node) => node.split(":")[0];
export function labelOf(node) {
  const branch = {
    scripts: "السكربتات",
    forms: "النماذج",
    document: "المستند",
  }[node.split(":")[1]];
  return branch || agents[roleOf(node)]?.[0] || node;
}
export const num = (value) => new Intl.NumberFormat("ar-EG").format(value);
export const dateText = (value) =>
  new Date(value).toLocaleString("ar-EG", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let body;
  try {
    body = await response.json();
  } catch {
    throw Error("الخدمة غير متاحة حاليًا. حاول مرة تانية.");
  }
  if (!response.ok)
    throw Error(
      typeof body.detail === "string" ? body.detail : "تعذّر تنفيذ الطلب.",
    );
  return body;
}
export const post = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export async function readRun(params, receive, signal) {
  const response = await fetch("/api/run", { ...post(params), signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw Error(
      typeof error.detail === "string" ? error.detail : "تعذّر بدء الفحص.",
    );
  }
  const stream = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    complete = false;
  function parse(line) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (!event || typeof event !== "object") throw Error("رد الفحص غير صالح.");
    if (event.type === "error")
      throw Error(event.message || "تعذّر إكمال الفحص.");
    if (event.type === "complete" && typeof event.report?.id === "string") {
      complete = true;
    } else if (event.type !== "step" || typeof event.node !== "string" || !Array.isArray(event.parents)) {
      throw Error("رد الفحص غير صالح.");
    }
    receive(event);
  }
  try {
    for (;;) {
      const { done, value } = await stream.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(parse);
      if (done) break;
    }
    parse(buffer);
    if (!complete) throw Error("انقطع الاتصال قبل وصول التقرير.");
  } finally {
    stream.releaseLock();
  }
}
