// The finding list may be ordered by the model. When it is, the page says so; otherwise it stays silent.
const note = { ar: "ترتيب الأولويات المقترح من الموديل", en: "Order suggested by the model" };

// Only a model-enriched report carries a trusted priority list.
export function suggestedPriority(report) {
  return report?.enrichment === "model" && Array.isArray(report.priority) ? report.priority : null;
}

export function modelOrderNote(priority, lang) {
  return priority?.length > 0 ? note[lang === "en" ? "en" : "ar"] : null;
}
