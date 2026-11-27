import React, { useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, SkipForward } from "lucide-react";
import AgentLanes from "./AgentLanes";
import { SPEEDS, canReplay, replayDelays } from "./replay";
import "./replay.css";

const KINDS = {
  queued: ["في الانتظار", "Queued"], running: ["قيد التنفيذ", "Running"], completed: ["مكتمل", "Completed"],
  partial: ["جزئي", "Partial"], failed: ["فشل", "Failed"], cancelled: ["أُلغي", "Cancelled"],
  model_skipped: ["الموديل لم يُستخدم", "Model not used"],
};
const HIDDEN_KINDS = new Set(["agent_done", "agent_start", "stage_start"]);

// Plays a stored scan's events back in order, so the live view can be shown when the provider is down.
// Nothing here calls the network: it only re-reads the events the page already loaded.
export default function ReplayPanel({ scan, events, t, lang, reportHref }) {
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [started, setStarted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const timer = useRef(null);
  const wanted = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("replay") === "1";
  const total = events.length;
  const ready = canReplay(scan, events);
  const finished = started && shown >= total;

  function begin() { setShown(0); setStarted(true); setPlaying(true); }
  useEffect(() => { if (wanted && ready && !started) begin(); }, [wanted, ready]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    clearTimeout(timer.current);
    if (!playing || shown >= total) { if (shown >= total) setPlaying(false); return undefined; }
    const delay = replayDelays(events, speed)[shown];
    timer.current = setTimeout(() => setShown((count) => count + 1), delay);
    return () => clearTimeout(timer.current);
  }, [playing, shown, speed, events, total]);

  if (!ready) return null;
  const visible = events.slice(0, shown);
  return (
    <section className="replay-panel" aria-label={t("إعادة عرض الفحص", "Scan replay")}>
      <h3>{t("إعادة عرض الفحص", "Replay this scan")}</h3>
      <p className="replay-note">{t("بيعيد عرض أحداث فحص محفوظ كما حصلت. مفيش طلبات للموديل ولا للشبكة.", "Plays back the stored events of this scan. No model or network requests are made.")}</p>
      <div className="replay-controls" role="group" aria-label={t("أزرار الإعادة", "Replay controls")}>
        {!started || finished
          ? <button type="button" className="btn primary" onClick={begin}><Play size={16} aria-hidden="true" />{finished ? t("أعد العرض", "Replay again") : t("ابدأ إعادة العرض", "Start replay")}</button>
          : <button type="button" className="btn" onClick={() => setPlaying((value) => !value)}>
            {playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}{playing ? t("إيقاف مؤقت", "Pause") : t("كمّل", "Resume")}</button>}
        {started && !finished && <button type="button" className="btn" onClick={() => { setShown(total); setPlaying(false); }}>
          <SkipForward size={16} aria-hidden="true" />{t("للنهاية", "Skip to end")}</button>}
        {started && <button type="button" className="btn" onClick={begin}><RotateCcw size={16} aria-hidden="true" />{t("من الأول", "Restart")}</button>}
        <label className="replay-speed">{t("السرعة", "Speed")}
          <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
            {SPEEDS.map((value) => <option key={value} value={value}>{value}x</option>)}
          </select>
        </label>
        {started && <span className="replay-count" role="status" data-testid="replay-count">
          {shown.toLocaleString(lang === "ar" ? "ar-EG" : "en")}/{total.toLocaleString(lang === "ar" ? "ar-EG" : "en")}</span>}
      </div>
      {started && <>
        <AgentLanes events={visible} active={!finished} t={t} lang={lang} />
        <ol className="replay-timeline" aria-label={t("أحداث الإعادة", "Replay events")}>
          {visible.filter((item) => !HIDDEN_KINDS.has(item.kind)).map((item) => <li key={item.sequence}>
            <b>{KINDS[item.kind] ? t(...KINDS[item.kind]) : item.kind}</b> <span dir="auto">{item.detail}</span>
          </li>)}
        </ol>
        {finished && reportHref && <p><a className="btn primary" href={reportHref}>{t("فتح التقرير", "Open report")}</a></p>}
      </>}
    </section>
  );
}
