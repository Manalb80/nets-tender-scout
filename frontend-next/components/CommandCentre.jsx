"use client";

/**
 * Leadership Command Centre: dark, high-density executive dashboard.
 * One scrollable view, no page navigation:
 *   1. Macro metric cards (flush, gapless stack)
 *   2. Horizontal 6-stage lifecycle funnel + bottleneck banner
 *   3. Actionable decisions & blockers queue
 *   4. Integrated Master RFP Register with filters and provenance tags
 *
 * Honest-data contract: built on the real pipeline snapshot. PKR values are
 * not in the snapshot (they live with the RFP analyses), so money figures are
 * omitted rather than invented; volume, scores, deadlines and decisions are real.
 *
 * Interactions:
 *   - Blocker click: filters + highlights the matching register row (scrolls to it)
 *   - Funnel stage click: filters the register by stage
 *   - Row / chevron: opens the Executive Details Drawer (never navigates)
 */

import { useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, ArrowRight, CalendarClock, CheckCircle2,
  ChevronRight, CircleDollarSign, Filter, Search, Target, TrendingUp, X,
} from "lucide-react";
import ExecutiveDetailsDrawer, { portalLink } from "./ExecutiveDetailsDrawer";

/* Same derivations the artifact uses, from the fields the snapshot carries */
const stageOf = (t) =>
  t.acqStatus === "AUTO_DOWNLOADED" || t.acqStatus === "MANUAL_UPLOADED" ? "RFP in Hand" : "Not Started";
const decisionOf = (t) => (t.goNogo === "GO" ? "GO" : t.goNogo === "NOGO" ? "NO-GO" : "Pending");

const STAGES = ["Not Started", "RFP in Hand", "Analysed", "Decided", "Submitted", "Outcome"];

/* Provenance tag: the trust vocabulary carried over from the artifact */
function Prov({ kind, title }) {
  const cls =
    kind === "OBS" ? "border-emerald-800 bg-emerald-950 text-emerald-400"
    : kind === "CALC" ? "border-slate-700 bg-slate-900 text-slate-400"
    : kind === "HUMAN" ? "border-amber-800 bg-amber-950 text-amber-400"
    : "border-slate-700 bg-slate-900 text-slate-500 border-dashed italic";
  return (
    <span title={title} className={`ml-1 inline-block cursor-help rounded border px-1 text-[9px] font-bold leading-4 ${cls}`}>
      {kind}
    </span>
  );
}

export default function CommandCentre({ tenders, exportedAt }) {
  const [stageF, setStageF] = useState("");
  const [vertF, setVertF] = useState("");
  const [decF, setDecF] = useState("");
  const [q, setQ] = useState("");
  const [hl, setHl] = useState(null);          // highlighted tender id (from blockers)
  const [sel, setSel] = useState(null);        // drawer tender
  const [open, setOpen] = useState(false);
  const regRef = useRef(null);

  /* ── derived sets ── */
  const verticals = useMemo(
    () => [...new Set(tenders.map((t) => t.solMatch?.[0]?.name).filter(Boolean))].sort(),
    [tenders]
  );

  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return tenders.filter(
      (t) =>
        (!stageF || stageOf(t) === stageF) &&
        (!vertF || t.solMatch?.[0]?.name === vertF) &&
        (!decF || decisionOf(t) === decF) &&
        (!ql || (t.ti + " " + t.id + " " + t.dept).toLowerCase().includes(ql))
    );
  }, [tenders, stageF, vertF, decF, q]);

  const byStage = useMemo(() => {
    const m = Object.fromEntries(STAGES.map((s) => [s, []]));
    tenders.forEach((t) => m[stageOf(t)].push(t));
    return m;
  }, [tenders]);

  const go = tenders.filter((t) => decisionOf(t) === "GO");
  const pending = tenders.filter((t) => decisionOf(t) === "Pending");
  const in7 = tenders.filter((t) => t.days <= 7);
  const in14 = tenders.filter((t) => t.days <= 14);

  /* ── action items: real blockers, derived, never invented ── */
  const actions = useMemo(() => {
    const items = [];
    for (const t of tenders) {
      const d = decisionOf(t), st = stageOf(t);
      if (d === "Pending" && t.days <= 14)
        items.push({ t, sev: t.days <= 7 ? 2 : 1, state: "Undecided", action: "Record GO / NO-GO", who: "Presales head" });
      else if (st === "Not Started" && t.days <= 10)
        items.push({ t, sev: t.days <= 5 ? 2 : 1, state: "No RFP in hand", action: "Download from portal, upload", who: "Sales" });
      else if (d === "GO" && !t.assignee)
        items.push({ t, sev: 1, state: "GO but unowned", action: "Assign a sales owner", who: "Sales lead" });
    }
    return items.sort((a, b) => b.sev - a.sev || a.t.days - b.t.days);
  }, [tenders]);

  /* ── bottleneck: the stage holding the most tenders closing within 14 days ── */
  const bottleneck = useMemo(() => {
    let worst = null;
    for (const s of STAGES.slice(0, 4)) {
      const soon = byStage[s].filter((t) => t.days <= 14);
      if (!worst || soon.length > worst.n) worst = { s, n: soon.length };
    }
    return worst && worst.n ? worst : null;
  }, [byStage]);

  const drillFromBlocker = (t) => {
    setHl(t.id); setStageF(""); setVertF(""); setDecF(""); setQ("");
    setTimeout(() => {
      const el = document.getElementById(`reg-${t.id}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
  };

  const openDrawer = (t) => { setSel(t); setOpen(true); };
  const maxStage = Math.max(...STAGES.map((s) => byStage[s].length), 1);

  return (
    /* Local dark scope: this page is dark-first regardless of the shell theme */
    <div className="dark">
      <div className="space-y-px rounded-2xl bg-slate-950 p-4 text-slate-100 sm:p-6">

        {/* ── 1. MACRO METRIC CARDS: flush, gapless, border-subtle ── */}
        <div className="grid overflow-hidden rounded-xl border border-slate-800 bg-slate-900 md:grid-cols-3 md:divide-x md:divide-slate-800">
          {/* Card 1: Q-o-Q */}
          <div className="border-b border-slate-800 p-5 md:border-b-0">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-500">
              <TrendingUp className="h-3.5 w-3.5 text-emerald-500" /> Quarter over quarter
            </p>
            <p className="mt-3 text-3xl font-extrabold tabular-nums tracking-tight">{tenders.length}</p>
            <p className="text-[12.5px] text-slate-400">live qualified this quarter</p>
            <p className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
              No prior-quarter history yet; growth, volume and win-rate deltas accrue from the engine&apos;s first full quarter.
            </p>
          </div>
          {/* Card 2: pipeline + forecast */}
          <div className="border-b border-slate-800 p-5 md:border-b-0">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-500">
              <CircleDollarSign className="h-3.5 w-3.5 text-emerald-500" /> Active pipeline
            </p>
            <div className="mt-3 flex items-baseline gap-5">
              <div><p className="text-3xl font-extrabold tabular-nums text-emerald-400">{go.length}</p><p className="text-[12.5px] text-slate-400">committed GO</p></div>
              <div><p className="text-3xl font-extrabold tabular-nums text-amber-400">{pending.length}</p><p className="text-[12.5px] text-slate-400">undecided</p></div>
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
              PKR values and the weighted forecast sync from the RFP analyses; shown in the live dashboard today.
            </p>
          </div>
          {/* Card 3: actions needed */}
          <div className="p-5">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-500">
              <Target className="h-3.5 w-3.5 text-amber-500" /> Decisions &amp; actions needed
            </p>
            <p className="mt-3 text-3xl font-extrabold tabular-nums text-amber-400">{actions.length}</p>
            <p className="text-[12.5px] text-slate-400">
              action items · <span className="text-red-400">{in7.length}</span> close in 7d · {in14.length} in 14d
            </p>
            <a href="#action-queue" className="mt-2 inline-flex items-center gap-1 text-[12px] font-semibold text-emerald-400 hover:text-emerald-300">
              Open the queue <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>

        {/* ── 2. LIFECYCLE FUNNEL ── */}
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="mb-4 text-[11px] font-bold uppercase tracking-widest text-slate-500">Lifecycle funnel</p>
          <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
            {STAGES.map((s, i) => {
              const n = byStage[s].length;
              const on = n > 0;
              const active = stageF === s;
              const soon = byStage[s].filter((t) => t.days <= 14).length;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStageF(active ? "" : s)}
                  className={`group relative min-w-[110px] flex-1 rounded-lg border p-3 text-left transition-all
                    ${active ? "border-emerald-500 ring-2 ring-emerald-500/30" : "border-slate-800 hover:border-slate-600"}
                    ${on ? "bg-slate-800/70" : "bg-slate-900 opacity-50"}`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{String(i + 1).padStart(2, "0")}</span>
                  <p className={`text-2xl font-extrabold tabular-nums ${on ? "text-white" : "text-slate-600"}`}>{n}</p>
                  <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-slate-400">{s}</p>
                  {/* density bar */}
                  <span className="mt-2 block h-1 overflow-hidden rounded-full bg-slate-800">
                    <span className="block h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500" style={{ width: `${Math.round((n / maxStage) * 100)}%` }} />
                  </span>
                  {soon > 0 && <p className="mt-1 text-[10.5px] font-semibold text-amber-400">{soon} close in 14d</p>}
                  {i < STAGES.length - 1 && (
                    <ChevronRight className="absolute -right-2 top-1/2 z-10 hidden h-4 w-4 -translate-y-1/2 text-slate-700 md:block" />
                  )}
                </button>
              );
            })}
          </div>
          {bottleneck && (
            <div className="mt-3 flex items-center gap-2.5 rounded-lg border border-amber-900/60 bg-amber-950/40 px-3.5 py-2.5 text-[13px] text-amber-200">
              <AlertTriangle className="h-4 w-4 flex-none text-amber-400" />
              <span>
                <b>Bottleneck:</b> {bottleneck.n} tender{bottleneck.n > 1 ? "s" : ""} closing within 14 days still at{" "}
                <b>{bottleneck.s}</b>.
                <button type="button" onClick={() => setStageF(bottleneck.s)} className="ml-2 font-semibold text-emerald-400 hover:text-emerald-300">
                  Filter the register →
                </button>
              </span>
            </div>
          )}
        </div>

        {/* ── 3. ACTION QUEUE ── */}
        <div id="action-queue" className="mt-3 scroll-mt-20 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-500">
            <Activity className="h-3.5 w-3.5 text-amber-500" /> Decisions &amp; blockers queue
            <span className="rounded-full bg-amber-950 px-2 py-0.5 text-[10.5px] font-bold text-amber-400">{actions.length}</span>
            <span className="ml-auto text-[11px] font-normal normal-case tracking-normal text-slate-500">Click an item to locate it in the register</span>
          </p>
          <div className="max-h-72 overflow-auto rounded-lg border border-slate-800">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-slate-950 text-left text-[10.5px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-2">Days</th><th className="px-3 py-2">Tender</th>
                  <th className="px-3 py-2">Owner</th><th className="px-3 py-2">Blocked state</th>
                  <th className="px-3 py-2">Required action</th><th className="px-3 py-2">Who acts</th>
                </tr>
              </thead>
              <tbody>
                {actions.map(({ t, sev, state, action, who }) => (
                  <tr
                    key={t.id + state}
                    onClick={() => drillFromBlocker(t)}
                    className="cursor-pointer border-t border-slate-800/70 transition-colors hover:bg-slate-800/60"
                  >
                    <td className={`px-3 py-2 font-extrabold tabular-nums ${sev === 2 ? "text-red-400" : "text-amber-400"}`}>{t.days}d</td>
                    <td className="max-w-[260px] truncate px-3 py-2 font-semibold text-slate-100">{t.ti}</td>
                    <td className="px-3 py-2 text-slate-400">{t.assignee || <span className="text-red-400">Unassigned</span>}</td>
                    <td className="px-3 py-2 font-semibold text-amber-300">{state}</td>
                    <td className="px-3 py-2 text-slate-300">{action}</td>
                    <td className="px-3 py-2 text-slate-400">{who}</td>
                  </tr>
                ))}
                {!actions.length && (
                  <tr><td colSpan={6} className="px-3 py-5 text-center text-slate-500"><CheckCircle2 className="mr-1 inline h-4 w-4 text-emerald-500" /> Nothing is blocked.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── 4. MASTER RFP REGISTER ── */}
        <div ref={regRef} className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">Master RFP register</p>
            <span className="text-[11px] text-slate-600">{filtered.length} of {tenders.length}</span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
                <input
                  value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, ID, buyer"
                  className="w-48 rounded-lg border border-slate-700 bg-slate-950 py-1.5 pl-8 pr-2.5 text-[12.5px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-emerald-600"
                />
              </div>
              {[
                [vertF, setVertF, ["", ...verticals], "All verticals"],
                [stageF, setStageF, ["", ...STAGES], "All stages"],
                [decF, setDecF, ["", "GO", "NO-GO", "Pending"], "All decisions"],
              ].map(([val, set, opts, label], i) => (
                <select key={i} value={val} onChange={(e) => set(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-[12.5px] text-slate-200 focus:border-emerald-600">
                  {opts.map((o) => <option key={o} value={o}>{o || label}</option>)}
                </select>
              ))}
              {(stageF || vertF || decF || q || hl) && (
                <button type="button" onClick={() => { setStageF(""); setVertF(""); setDecF(""); setQ(""); setHl(null); }}
                  className="flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-[12px] font-semibold text-slate-300 hover:border-red-700 hover:text-red-400">
                  <X className="h-3 w-3" /> Clear
                </button>
              )}
            </div>
          </div>
          <div className="max-h-[560px] overflow-auto rounded-lg border border-slate-800">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 z-10 bg-slate-950 text-left text-[10.5px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-2.5">Days</th><th className="px-3 py-2.5">Tender</th>
                  <th className="px-3 py-2.5">Vertical</th><th className="px-3 py-2.5">Stage</th>
                  <th className="px-3 py-2.5">Score</th><th className="px-3 py-2.5">Decision</th><th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => {
                  const lk = portalLink(t); const d = decisionOf(t); const st = stageOf(t);
                  return (
                    <tr
                      key={t.id} id={`reg-${t.id}`}
                      onClick={() => openDrawer(t)}
                      className={`cursor-pointer border-t border-slate-800/70 transition-colors hover:bg-slate-800/60
                        ${hl === t.id ? "bg-emerald-950/60 ring-1 ring-inset ring-emerald-600" : ""}`}
                    >
                      <td className={`px-3 py-2 font-extrabold tabular-nums ${t.days <= 3 ? "text-red-400" : t.days <= 7 ? "text-amber-400" : "text-slate-400"}`}>
                        {t.days}d<Prov kind="OBS" title="Closing date read from the portal listing" />
                      </td>
                      <td className="max-w-[300px] px-3 py-2">
                        <a href={lk.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                          title={lk.exact ? "Open this tender on its source portal" : "Exact link not stored; opens the portal listing"}
                          className="block truncate border-b border-dotted border-slate-600 font-semibold text-slate-100 hover:text-emerald-400">
                          {t.ti}
                        </a>
                        <span className="text-[11px] text-slate-500">{t.id} · {t.source}</span>
                      </td>
                      <td className="px-3 py-2 text-slate-400">{t.solMatch?.[0]?.name || "—"}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[10.5px] font-bold ${st === "RFP in Hand" ? "border-emerald-800 bg-emerald-950 text-emerald-400" : "border-slate-700 bg-slate-900 text-slate-400"}`}>{st}</span>
                      </td>
                      <td className="px-3 py-2 font-bold tabular-nums">{t.score}<Prov kind="CALC" title="Scored by the official NETS scorer from the listing title" /></td>
                      <td className={`px-3 py-2 font-bold ${d === "GO" ? "text-emerald-400" : d === "NO-GO" ? "text-slate-500" : "text-amber-400"}`}>
                        {d}{d !== "Pending" && <Prov kind="HUMAN" title="Set by a person on the Sales board" />}
                      </td>
                      <td className="px-3 py-2">
                        <button type="button" onClick={(e) => { e.stopPropagation(); openDrawer(t); }}
                          className="rounded-lg border border-slate-700 px-2.5 py-1 text-[11.5px] font-semibold text-slate-300 transition-colors hover:border-emerald-600 hover:text-emerald-400">
                          View
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {!filtered.length && <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-500">No tender matches these filters.</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-600">
            <CalendarClock className="h-3.5 w-3.5" /> Snapshot exported {exportedAt?.slice(0, 16).replace("T", " ")} · provenance: OBS read from the portal, CALC computed by the scorer, HUMAN set by a person. Values marked EST never appear here; money figures sync with the RFP analyses.
          </p>
        </div>
      </div>

      <ExecutiveDetailsDrawer
        open={open}
        tender={sel}
        analysis={{}}
        pipeline={{ stage: sel ? (stageOf(sel) === "RFP in Hand" ? "RFP in hand" : "Not started") : "Not started", owner: sel?.assignee || "Unassigned", decision: sel ? decisionOf(sel) : "Pending" }}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}
