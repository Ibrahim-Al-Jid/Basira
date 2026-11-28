import { post } from "./data";

export const api = "/api/platform";
export const translate = (lang) => (ar, en) => lang === "en" ? en : ar;
// English text for the server messages a user can act on. Other server text stays Arabic-only.
const knownErrors = {
  "اللقطة خالية من الملفات النصية المدعومة.": "The snapshot has no supported source files. Basira reads code and config files (.py, .js, .ts, .json, .yaml, .toml, .xml, Dockerfile and similar), not Markdown, images or empty folders.",
  "عدد عناصر ZIP لازم يكون بين ١ و٢٠٠.": "The snapshot must contain between 1 and 200 entries.",
  "حجم ملفات ZIP بعد الفك تجاوز الحد.": "The unpacked size of the snapshot is over the limit (8 MB). Scan a smaller repository.",
  "ZIP فيه أسماء مكررة.": "The snapshot has duplicate file names.",
  "ZIP يحتوي على رابط أو ملف خاص أو طريقة ضغط غير مدعومة.": "The snapshot has a symbolic link, special file or unsupported compression.",
  "الأرشيفات المتداخلة غير مدعومة.": "Nested archives are not supported.",
  "نسبة ضغط ملف داخل ZIP تجاوزت الحد.": "A file in the snapshot has a compression ratio over the limit.",
  "ملف نصي في اللقطة مش بترميز UTF-8 صالح.": "A text file in the snapshot is not valid UTF-8.",
  "ملف نصي في اللقطة تجاوز الحدود أو فيه بيانات ثنائية.": "A text file in the snapshot is over 1 MB or contains binary data.",
  "الفرع أو معرّف النسخة غير صالح.": "The branch or commit identifier is not valid.",
  "عدد مواضع الأدلة تجاوز الحد. قسّم اللقطة إلى ملفات أصغر.": "The snapshot has too many evidence locations. Split it into smaller files.",
  "الملف لازم يكون ZIP صالح.": "The file must be a valid ZIP.",
  "لقطة المستودع لازم تكون ZIP صالح.": "The repository snapshot must be a valid ZIP.",
  "معرّف GitHub خارج النطاق المدعوم.": "The GitHub identifier is outside the supported range.",
  "المستودع خارج صلاحيات GitHub الحالية.": "The repository is outside the current GitHub permissions. Add it to the GitHub App's selected repositories and refresh the list.",
  "GitHub رفض الوصول للمستودع أو النسخة المطلوبة.": "GitHub refused access to the repository or the requested branch or commit. Check the branch name.",
  "اربط حسابك بـGitHub من جديد.": "Connect your GitHub account again.",
  "اتصال GitHub اتغيّر قبل تسجيل الفحص.": "The GitHub connection changed before the scan was recorded. Try again.",
  "GitHub تعذّر عليه إرجاع اللقطة.": "GitHub could not return the snapshot. Try again.",
};
const isArabic = (text) => /[\u0600-\u06ff]/.test(text);
// A browser network failure has no HTTP status and an English engine message ("Failed to fetch").
const isNetwork = (err) => err instanceof TypeError || (!err.status && /^(failed to fetch|load failed|networkerror)/i.test(err.message));
export const errorText = (err, t) => {
  if (isNetwork(err)) return t("تعذّر الاتصال بالخادم. اتأكد من الإنترنت وحاول تاني.", "Could not reach the server. Check your connection and try again.");
  const english = knownErrors[err.message] || ({
    401: "Check your credentials or sign in again.",
    403: "This account cannot perform the requested action.",
    404: "This item is unavailable.",
    409: "This item already exists or its state changed.",
    422: "Check the form values and try again.",
    429: "Too many requests. Wait a moment and try again.",
  })[err.status] || (/^[\x00-\x7f]+$/.test(err.message) ? err.message : "The request could not be completed.");
  return t(isArabic(err.message) ? err.message : "تعذّر تنفيذ الطلب.", english);
};
export const json = (method, body) => ({ ...post(body), method });

export async function action(path, options) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status === 429 ? "محاولات كتير في وقت قصير. استنى شوية وحاول تاني." : "تعذّر تنفيذ الطلب.";
    throw Object.assign(Error(typeof value?.detail === "string" ? value.detail : fallback), {
      status: response.status,
      fields: Array.isArray(value?.fields) ? value.fields : [],
    });
  }
  return value;
}
