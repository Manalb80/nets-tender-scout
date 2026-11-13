"use client";

/**
 * Executive Details Drawer: production port of the Task 1 leadership drawer.
 *
 * Right-hand slide-out panel. Opening or closing it never navigates; the
 * dashboard behind it is untouched. Two tabs keep the two AI outputs apart:
 *   - Executive overview: value, deadline, score, decision, stage, next action
 *   - RFP details: Agent 2 analysis, labelled CONFIRMED; falls back to the
 *     listing brief labelled INDICATIVE, or a clear "not yet analysed" notice.
 *
 * Interaction contract (mirrors the artifact version, all tests ported):
 *   - Esc closes; backdrop click closes; X closes
 *   - Tender name in the header links to the EXACT source portal page when one
 *     is stored or derivable (PPRA TS id); a generic listing is labelled as such
 *   - Controlled component: <ExecutiveDetailsDrawer open tender={t} analysis={a} onClose={fn} />
 */

import { useEffect, useMemo, useState } from "react";

/* ── Portal link with exactness, identical rules to the artifact ── */
export function portalLink(t) {
  if (t?.detailUrl) return { url: t.detailUrl, exact: true };
  const src = t?.portal || t?.source || "Sindh Bank";
  if (src.includes("PPRA")) {
    const m = String(t?.id || "").match(/TS\d+E/);
    if (m) return { url: `https://epms.ppra.gov.pk/public/tenders/tender-details/${m[0]}`, exact: true };
    return { url: "https://epms.ppra.gov.pk/public/tenders/active-tenders", exact: false };
  }
  if (src.includes("EPADS")) return { url: "https://eprocure.gov.pk/", exact: false };
  return { url: "https://sindhbank.com.pk/tenders", exact: false };
}

const fmtPKR = (n) => {
  n = n || 0;
  if (n >= 1e9) return `PKR ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `PKR ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `PKR ${(n / 1e3).toFixed(0)}K`;
  return `PKR ${n}`;
};

/* ── Small building blocks ── */
function SourceBadge({ kind }) {
  // kind: "rfp" (confirmed from the document) | "listing" (indicative)
  const rfp = kind === "rfp";
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-bold tracking-wide
        ${rfp
          ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
          : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"}`}
    >
      {rfp ? "Confirmed · from RFP" : "Indicative · portal listing"}
    </span>
  );
}

function SectionLabel({ children }) {
  return (
    <p className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
      {children}
    </p>
  );
}

function KCard({ label, value, sub, tone }) {
  const toneCls =
    tone === "danger" ? "text-red-600 dark:text-red-400"
    : tone === "warn" ? "text-amber-600 dark:text-amber-400"
    : tone === "ok" ? "text-emerald-600 dark:text-emerald-400"
    : "text-slate-900 dark:text-white";
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 dark:border-slate-800 dark:bg-slate-950">
      <p className="text-[11.5px] text-slate-400 dark:text-slate-500">{label}</p>
      <p className={`mt-0.5 text-[15px] font-bold ${toneCls}`}>{value}</p>
      {sub ? <p className="text-[11.5px] text-slate-400 dark:text-slate-500">{sub}</p> : null}
    </div>
  );
}

function StageBar({ stage }) {
  const STAGES = ["Not started", "RFP in hand", "Analysed", "Decided", "Submitted", "Won"];
  const idx = Math.max(0, STAGES.indexOf(stage === "Lost" ? "Submitted" : stage));
  return (
    <span className="flex w-28 gap-0.5" title={stage} aria-label={`Stage: ${stage}`}>
      {STAGES.map((s, i) => (
        <span
          key={s}
          className={`h-1.5 flex-1 rounded-full ${
            stage === "Lost" && i === idx ? "bg-red-500"
            : i < idx ? "bg-emerald-500"
            : i === idx ? "bg-amber-400"
            : "bg-slate-200 dark:bg-slate-700"}`}
        />
      ))}
    </span>
  );
}

function Bullets({ items, tone }) {
  if (!items?.length) return null;
  return (
    <ul className="ml-4 list-disc space-y-1 text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">
      {items.map((x, i) => (
        <li key={i} className={tone === "danger" ? "text-red-600 dark:text-red-400" : undefined}>{x}</li>
      ))}
    </ul>
  );
}

/* ── Tab bodies ── */
function ExecOverview({ tender, analysis, pipeline }) {
  const g = analysis?.grading;
  const lb = analysis?.listing_brief;
  const days = tender?.days;
  const decision = pipeline?.decision || analysis?.decision?.bid_decision || "Pending";
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-2.5">
        <KCard label="Estimated value" value={fmtPKR(pipeline?.estValue)} sub={pipeline?.estValueProvenance} />
        <KCard
          label="Closing"
          value={days == null ? "?" : `${days} days`}
          sub={tender?.cl || "date TBD"}
          tone={days != null && days <= 3 ? "danger" : days != null && days <= 7 ? "warn" : undefined}
        />
        <KCard label="Qualification score" value={`${tender?.score ?? 0}/100`} sub={tender?.verdict} />
        <KCard
          label="Bid decision"
          value={decision}
          tone={decision === "BID" ? "ok" : decision === "NO-BID" ? undefined : "warn"}
        />
      </div>

      <div>
        <SectionLabel>Where it stands</SectionLabel>
        <div className="flex items-center gap-3">
          <StageBar stage={pipeline?.stage || "Not started"} />
          <span className="text-sm font-bold text-slate-900 dark:text-white">{pipeline?.stage || "Not started"}</span>
        </div>
        {pipeline?.nextAction ? (
          <p className="mt-2 text-[13px] text-slate-700 dark:text-slate-300">
            <b>Next action:</b> {pipeline.nextAction.txt}{" "}
            <span className="text-slate-400">({pipeline.nextAction.who})</span>
          </p>
        ) : null}
        <p className="mt-1 text-[13px] text-slate-700 dark:text-slate-300">
          <b>Owner:</b>{" "}
          <span className={pipeline?.owner === "Unassigned" ? "font-semibold text-red-600 dark:text-red-400" : undefined}>
            {pipeline?.owner || "Unassigned"}
          </span>
          {tender?.dept ? <> · <b>Buyer:</b> {tender.dept}</> : null}
        </p>
      </div>

      <div>
        <SectionLabel>NETS verticals matched</SectionLabel>
        <div className="flex flex-wrap gap-1.5">
          {(tender?.solMatch?.length ? tender.solMatch : []).map((s) => (
            <span key={s.id || s.name} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {s.name || s.id}
            </span>
          ))}
          {!tender?.solMatch?.length && <span className="text-[13px] text-slate-400">None recorded</span>}
        </div>
      </div>

      {g ? (
        <div>
          <SectionLabel>Bid assessment <SourceBadge kind="rfp" /></SectionLabel>
          <p className="text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">
            Readiness <b>{g.readiness_pct != null ? `${g.readiness_pct}%` : "?"}</b>, verdict <b>{g.verdict}</b>, confidence {g.confidence}.
            {g.risks?.length ? <> Top risk: {g.risks[0].risk}.</> : null}
          </p>
        </div>
      ) : null}

      {lb ? (
        <div>
          <SectionLabel>Opportunity summary <SourceBadge kind="listing" /></SectionLabel>
          <p className="text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">{lb.what_it_appears_to_be}</p>
        </div>
      ) : null}

      {!g && !lb ? (
        <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3.5 text-[13px] leading-relaxed text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
          No summary generated yet. The Architect workbench can produce a listing brief without the RFP,
          and the full analysis once the document is in hand.
        </p>
      ) : null}
    </div>
  );
}

function RfpDetails({ tender, analysis }) {
  const sm = analysis?.summary;
  const c = analysis?.compliance;
  const g = analysis?.grading;
  const lb = analysis?.listing_brief;

  if (!sm && !c && !g) {
    return (
      <div className="space-y-6">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[13px] leading-relaxed text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <b>RFP not yet analysed.</b>{" "}
          {analysis?.rfpText
            ? "The document is in hand; the four Step 2 analyses have not been run."
            : `The RFP document has not been obtained. Acquisition status: ${String(tender?.acqStatus || "pending").replace(/_/g, " ").toLowerCase()}.`}
        </div>
        {lb ? (
          <div>
            <SectionLabel>What the listing suggests <SourceBadge kind="listing" /></SectionLabel>
            <p className="mb-3 text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">{lb.what_it_appears_to_be}</p>
            {lb.unknowns_to_confirm?.length ? (
              <>
                <SectionLabel>Only the RFP can answer</SectionLabel>
                <Bullets items={lb.unknowns_to_confirm} />
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  const eligibility = [];
  const el = sm?.eligibility || {};
  if (el.min_turnover) eligibility.push(`Minimum turnover: ${el.min_turnover}`);
  if (el.years_experience) eligibility.push(`Experience: ${el.years_experience}`);
  (el.certifications || []).slice(0, 4).forEach((x) => eligibility.push(`Certification: ${x}`));
  (el.oem_requirements || []).slice(0, 3).forEach((x) => eligibility.push(`OEM requirement: ${x}`));

  const tl = sm?.timeline || {};
  const deadlines = [
    tl.submission_deadline && ["Submission", tl.submission_deadline],
    tl.bid_validity && ["Bid validity", tl.bid_validity],
    tl.delivery_period && ["Delivery", tl.delivery_period],
    tl.contract_duration && ["Contract", tl.contract_duration],
  ].filter(Boolean);

  return (
    <div className="space-y-6">
      {sm ? (
        <>
          <div>
            <SectionLabel>Scope <SourceBadge kind="rfp" /></SectionLabel>
            <p className="text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">{sm.scope_summary}</p>
          </div>
          {sm.key_requirements?.length ? (
            <div><SectionLabel>Key requirements</SectionLabel><Bullets items={sm.key_requirements.slice(0, 8)} /></div>
          ) : null}
          {eligibility.length ? (
            <div><SectionLabel>Eligibility</SectionLabel><Bullets items={eligibility} /></div>
          ) : null}
          {deadlines.length ? (
            <div>
              <SectionLabel>Deadlines and durations</SectionLabel>
              <div className="grid grid-cols-2 gap-2.5">
                {deadlines.map(([l, v]) => <KCard key={l} label={l} value={String(v)} />)}
              </div>
            </div>
          ) : null}
          {sm.red_flags?.length ? (
            <div><SectionLabel><span className="text-red-500">Red flags</span></SectionLabel><Bullets items={sm.red_flags.slice(0, 5)} tone="danger" /></div>
          ) : null}
        </>
      ) : null}

      {c ? (
        <div>
          <SectionLabel>Mandatory documents <SourceBadge kind="rfp" /></SectionLabel>
          <p className="text-[13px] text-slate-700 dark:text-slate-300">
            <b className="text-emerald-600 dark:text-emerald-400">{c.have_count || 0}</b> have ·{" "}
            <b className="text-amber-600 dark:text-amber-400">{c.prepare_count || 0}</b> to prepare ·{" "}
            <b className="text-red-600 dark:text-red-400">{c.missing_count || 0}</b> missing
          </p>
          <Bullets items={(c.critical_gaps || []).slice(0, 4)} tone="danger" />
        </div>
      ) : null}

      {g?.risks?.length ? (
        <div>
          <SectionLabel>Risks</SectionLabel>
          <Bullets items={g.risks.slice(0, 5).map((r) => `${(r.severity || "").toUpperCase()}: ${r.risk}`)} />
        </div>
      ) : null}

      <p className="text-xs leading-relaxed text-slate-400 dark:text-slate-500">
        Generated by the RFP analyses under the evidence rule: claims without a verbatim RFP quote are
        flagged unverified in the Architect workbench.
      </p>
    </div>
  );
}

/* ── The drawer shell ── */
export default function ExecutiveDetailsDrawer({ open, tender, analysis, pipeline, onClose }) {
  const [tab, setTab] = useState("exec");
  const lk = useMemo(() => portalLink(tender), [tender]);

  useEffect(() => { if (open) setTab("exec"); }, [open, tender?.id]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        aria-hidden
        className={`fixed inset-0 z-40 bg-slate-950/45 transition-opacity duration-200
          ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
      />
      {/* Panel */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={tender ? `Details: ${tender.ti || tender.title}` : "Tender details"}
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-2xl transition-transform duration-300 ease-[cubic-bezier(.32,.72,.33,1)] dark:bg-slate-900
          ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        {tender ? (
          <>
            <header className="relative border-b border-slate-200 p-6 pb-4 dark:border-slate-800">
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition-colors hover:border-red-300 hover:text-red-500 dark:border-slate-700"
              >
                ✕
              </button>
              <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                {tender.portal || tender.source} · {tender.id}
              </p>
              <h2 className="pr-9 text-[17px] font-extrabold leading-snug tracking-tight text-slate-900 dark:text-white">
                {tender.ti || tender.title}
              </h2>
              <a
                href={lk.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block text-[12.5px] font-semibold text-emerald-600 hover:underline dark:text-emerald-400"
              >
                {lk.exact
                  ? "Open this tender on the source portal ↗"
                  : "Exact source link not stored; opens the portal listing ↗"}
              </a>
            </header>

            <nav className="flex gap-0.5 border-b border-slate-200 px-6 dark:border-slate-800" role="tablist">
              {[["exec", "Executive overview"], ["rfp", "RFP details"]].map(([k, label]) => (
                <button
                  key={k}
                  role="tab"
                  aria-selected={tab === k}
                  onClick={() => setTab(k)}
                  className={`border-b-2 px-4 py-2.5 text-[13px] font-semibold transition-colors
                    ${tab === k
                      ? "border-emerald-500 text-emerald-600 dark:text-emerald-400"
                      : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"}`}
                >
                  {label}
                </button>
              ))}
            </nav>

            <div className="flex-1 overflow-y-auto p-6">
              {tab === "exec"
                ? <ExecOverview tender={tender} analysis={analysis} pipeline={pipeline} />
                : <RfpDetails tender={tender} analysis={analysis} />}
            </div>
          </>
        ) : null}
      </aside>
    </>
  );
}
