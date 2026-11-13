"use client";

/**
 * Leadership overview: production port of the artifact's "Where we stand" view.
 *
 * Same interaction contract as Task 1:
 *   - Tender name: opens the EXACT source portal page in a new tab (portalLink)
 *   - Row or View: opens the Executive Details Drawer; never navigates away
 *
 * Data comes in as props (today: data/pipeline_snapshot.json exported from the
 * artifact DB; later: the pipeline API). Stage and decision are derived with
 * the same rules the artifact uses, from the fields the snapshot carries.
 */

import { useMemo, useState } from "react";
import ExecutiveDetailsDrawer, { portalLink } from "./ExecutiveDetailsDrawer";

const stageOf = (t) =>
  t.acqStatus === "AUTO_DOWNLOADED" || t.acqStatus === "MANUAL_UPLOADED" ? "RFP in hand" : "Not started";
const decisionOf = (t) => (t.goNogo === "GO" ? "Sales: GO" : t.goNogo === "NOGO" ? "Sales: NO-GO" : "Pending");

function Tile({ label, value, sub, tone, onClick }) {
  const v =
    tone === "danger" ? "text-red-600 dark:text-red-400"
    : tone === "warn" ? "text-amber-600 dark:text-amber-400"
    : tone === "ok" ? "text-emerald-600 dark:text-emerald-400"
    : "text-slate-900 dark:text-white";
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-card transition-colors hover:border-brand dark:border-slate-800 dark:bg-slate-900"
    >
      <p className="text-[12.5px] font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1.5 text-[26px] font-extrabold leading-none tracking-tight ${v}`}>{value}</p>
      {sub ? <p className="mt-2 text-[12.5px] leading-snug text-slate-400 dark:text-slate-500">{sub}</p> : null}
    </button>
  );
}

function StageCells({ t }) {
  const st = stageOf(t);
  const done = st === "RFP in hand" ? 1 : 0;
  return (
    <span className="flex w-24 gap-0.5" title={st}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`h-1.5 flex-1 rounded-full ${i < done ? "bg-emerald-500" : i === done ? "bg-amber-400" : "bg-slate-200 dark:bg-slate-700"}`} />
      ))}
    </span>
  );
}

export default function LeadershipOverview({ tenders, exportedAt }) {
  const [portal, setPortal] = useState("all");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null); // tender for the drawer
  const [open, setOpen] = useState(false);

  const live = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return tenders.filter(
      (t) =>
        (portal === "all" || t.source === portal) &&
        (!ql || (t.ti + " " + t.id + " " + t.dept).toLowerCase().includes(ql))
    );
  }, [tenders, portal, q]);

  const in7 = live.filter((t) => t.days <= 7);
  const in14 = live.filter((t) => t.days <= 14);
  const unassigned = live.filter((t) => !t.assignee);
  const undecided = live.filter((t) => decisionOf(t) === "Pending");

  const openDrawer = (t) => { setSel(t); setOpen(true); };

  /* By vertical rollup */
  const verticals = useMemo(() => {
    const m = new Map();
    for (const t of live) {
      const key = t.solMatch?.[0]?.name || "Other";
      if (!m.has(key)) m.set(key, { n: 0, go: 0, und: 0, soon: 0 });
      const r = m.get(key);
      r.n++;
      if (t.goNogo === "GO") r.go++;
      else if (t.goNogo !== "NOGO") r.und++;
      if (t.days <= 14) r.soon++;
    }
    return [...m.entries()].sort((a, b) => b[1].n - a[1].n);
  }, [live]);

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Live qualified tenders" value={live.length} sub="Score 70+, open, not NO-GO" tone="ok" />
        <Tile label="Closing in 7 / 14 days" value={`${in7.length} / ${in14.length}`} sub="Portal deadlines" tone={in7.length ? "warn" : undefined} />
        <Tile label="Undecided" value={undecided.length} sub="No GO / NO-GO recorded yet" tone={undecided.length ? "warn" : undefined} />
        <Tile label="Unassigned" value={unassigned.length} sub="No sales owner recorded" tone={unassigned.length ? "danger" : "ok"} />
      </div>

      {/* By vertical */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <p className="mb-3 text-[13px] font-bold uppercase tracking-wider text-slate-900 dark:text-white">By vertical</p>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11.5px] uppercase tracking-wider text-slate-400 dark:border-slate-700">
                <th className="py-2 pr-4">Vertical</th>
                <th className="py-2 pr-4 text-right">Live</th>
                <th className="py-2 pr-4 text-right">GO</th>
                <th className="py-2 pr-4 text-right">Undecided</th>
                <th className="py-2 text-right">Close in 14d</th>
              </tr>
            </thead>
            <tbody>
              {verticals.map(([name, r]) => (
                <tr key={name} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-4 font-semibold text-slate-900 dark:text-white">{name}</td>
                  <td className="py-2 pr-4 text-right">{r.n}</td>
                  <td className="py-2 pr-4 text-right font-bold text-emerald-600 dark:text-emerald-400">{r.go}</td>
                  <td className={`py-2 pr-4 text-right font-bold ${r.und ? "text-amber-600 dark:text-amber-400" : ""}`}>{r.und}</td>
                  <td className={`py-2 text-right ${r.soon ? "font-bold text-red-600 dark:text-red-400" : ""}`}>{r.soon}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Register */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <p className="text-[13px] font-bold uppercase tracking-wider text-slate-900 dark:text-white">RFP register</p>
          <p className="text-xs text-slate-400">Tender name opens the source portal; View opens the details panel.</p>
          <div className="ml-auto flex items-center gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search title, ID, buyer"
              className="w-52 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-[13px] outline-none focus:border-emerald-400 dark:border-slate-700 dark:bg-slate-950"
            />
            <select
              value={portal}
              onChange={(e) => setPortal(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[13px] dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="all">All portals</option>
              <option>PPRA</option>
              <option>EPADS</option>
              <option>Sindh Bank</option>
            </select>
          </div>
        </div>
        <div className="max-h-[560px] overflow-auto rounded-lg border border-slate-100 dark:border-slate-800">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-slate-50 dark:bg-slate-950">
              <tr className="text-left text-[11.5px] uppercase tracking-wider text-slate-400">
                <th className="px-3 py-2.5">Days</th>
                <th className="px-3 py-2.5">Tender</th>
                <th className="px-3 py-2.5">Vertical</th>
                <th className="px-3 py-2.5">Stage</th>
                <th className="px-3 py-2.5">Score</th>
                <th className="px-3 py-2.5">Decision</th>
                <th className="px-3 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {live.map((t) => {
                const lk = portalLink(t);
                const d = decisionOf(t);
                return (
                  <tr
                    key={t.id}
                    onClick={() => openDrawer(t)}
                    className="cursor-pointer border-b border-slate-100 transition-colors hover:bg-emerald-50/40 dark:border-slate-800 dark:hover:bg-slate-800/60"
                  >
                    <td className={`px-3 py-2.5 font-extrabold ${t.days <= 3 ? "text-red-600" : t.days <= 7 ? "text-amber-600" : "text-slate-500"}`}>{t.days}d</td>
                    <td className="max-w-xs px-3 py-2.5">
                      <a
                        href={lk.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        title={lk.exact ? "Open this tender on its source portal" : "Exact tender link not stored; opens the portal listing"}
                        className="block truncate border-b border-dotted border-slate-300 font-semibold text-slate-900 hover:text-emerald-700 dark:text-white"
                      >
                        {t.ti}
                      </a>
                      <span className="text-xs text-slate-400">{t.id} · {t.source}</span>
                    </td>
                    <td className="px-3 py-2.5 text-slate-600 dark:text-slate-300">{t.solMatch?.[0]?.name || "—"}</td>
                    <td className="px-3 py-2.5"><StageCells t={t} /></td>
                    <td className="px-3 py-2.5 font-bold">{t.score}</td>
                    <td className={`px-3 py-2.5 font-bold ${d === "Sales: GO" ? "text-emerald-600" : d === "Sales: NO-GO" ? "text-slate-400" : "text-amber-600"}`}>{d}</td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); openDrawer(t); }}
                        className="rounded-lg border border-slate-200 px-3 py-1 text-xs font-semibold transition-colors hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!live.length && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-400">No tender matches these filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Snapshot exported {exportedAt?.slice(0, 16).replace("T", " ")} from the live dashboard database. Analyses and bid
          decisions arrive with the pipeline API port; the drawer shows acquisition status meanwhile.
        </p>
      </div>

      <ExecutiveDetailsDrawer
        open={open}
        tender={sel}
        analysis={{}}
        pipeline={{ stage: sel ? stageOf(sel) : "Not started", owner: sel?.assignee || "Unassigned", decision: sel ? decisionOf(sel) : "Pending" }}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}
