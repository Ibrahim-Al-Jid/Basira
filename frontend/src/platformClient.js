import { post } from "./data";

export const api = "/api/platform";
export const translate = (lang) => (ar, en) => lang === "en" ? en : ar;
export const errorText = (err, t) => t(err.message, ({
  401: "Check your credentials or sign in again.",
  403: "This account cannot perform the requested action.",
  404: "This item is unavailable.",
  409: "This item already exists or its state changed.",
  422: "Check the form values and try again.",
  429: "Too many requests. Wait a moment and try again.",
})[err.status] || (/^[\x00-\x7f]+$/.test(err.message) ? err.message : "The request could not be completed."));
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
