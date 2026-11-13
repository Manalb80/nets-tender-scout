"use client";

/**
 * Knowledge Bank browser: production port of the artifact's Knowledge bank view.
 *
 * Read-only library of every past proposal the writer draws on: the seed PDFs
 * plus proposals approved in the dashboard (Agent 6, origin "approved").
 *
 * Data contract (matches scripts/kb/build_kb.py and agent6_rebuild_kb.py output):
 *   chunks: [{ id, source, client, section, text, words, terms[], verticals[], origin }]
 *   solutionNames: { [verticalId]: "Display name" }   (from backend/scorer.py SOLUTIONS)
 *
 * Features: phrase search with <mark> highlights, vertical filter with counts,
 * proposals/paragraphs mode, split list + reader with a section jump dropdown.
 * Approved-in-dashboard files carry a green badge. Pure props + local state:
 * no fetching, no globals, nothing leaks outside the .nets-next scope.
 */

import { useMemo, useState } from "react";

const escapeReg = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function Highlight({ text, q }) {
  if (!q) return <>{text}</>;
  const parts = String(text).split(new RegExp(`(${escapeReg(q)})`, "ig"));
  return (
    <>
      {parts.map((p, i) =>
        p.toLowerCase() === q.toLowerCase()
          ? <mark key={i} className="rounded-sm bg-yellow-200 px-0.5 text-inherit dark:bg-yellow-700">{p}</mark>
          : <span key={i}>{p}</span>
      )}
    </>
  );
}

function Tile({ label, value, sub, tone }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      <p className="text-[12.5px] font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1.5 text-[26px] font-extrabold leading-none tracking-tight ${tone === "danger" ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-white"}`}>{value}</p>
      {sub ? <p className="mt-2 text-[12.5px] leading-relaxed text-slate-400 dark:text-slate-500">{sub}</p> : null}
    </div>
  );
}

export default function KnowledgeBankBrowser({ chunks = [], solutionNames = {} }) {
  const [q, setQ] = useState("");
  const [vertical, setVertical] = useState("");
  const [mode, setMode] = useState("proposals"); // proposals | paragraphs
  const [openFile, setOpenFile] = useState(null);
  const [section, setSection] = useState("");

  const nameOf = (id) => solutionNames[id] || id;

  /* Group chunks by source file */
  const files = useMemo(() => {
    const map = new Map();
    for (const c of chunks) {
      if (!map.has(c.source)) {
        map.set(c.source, { source: c.source, client: c.client, verticals: c.verticals || [], chunks: [], words: 0, approved: c.origin === "approved" });
      }
      const f = map.get(c.source);
      f.chunks.push(c);
      f.words += c.words || 0;
    }
    return [...map.values()].sort((a, b) => (b.approved ? 1 : 0) - (a.approved ? 1 : 0) || a.client.localeCompare(b.client));
  }, [chunks]);

  /* Vertical counts for the filter */
  const verticalCounts = useMemo(() => {
    const vc = {};
    for (const f of files) for (const v of f.verticals) vc[v] = (vc[v] || 0) + 1;
    return vc;
  }, [files]);

  const ql = q.trim().toLowerCase();
  const matches = (f) => {
    if (vertical && !f.verticals.includes(vertical)) return false;
    if (!ql) return true;
    if ((f.client + " " + f.source).toLowerCase().includes(ql)) return true;
    return f.chunks.some((c) => c.text.toLowerCase().includes(ql));
  };
  const shown = files.filter(matches);

  const current = openFile ? files.find((f) => f.source === openFile) : null;
  const currentSections = current ? [...new Set(current.chunks.map((c) => c.section))] : [];
  const readerChunks = current
    ? current.chunks.filter((c) => (!section || c.section === section) && (!ql || mode !== "paragraphs" || c.text.toLowerCase().includes(ql)))
    : [];

  /* Paragraph mode: flat hit list across all files */
  const paragraphHits = useMemo(() => {
    if (mode !== "paragraphs" || !ql) return [];
    return chunks.filter((c) => c.text.toLowerCase().includes(ql)).slice(0, 80);
  }, [mode, ql, chunks]);

  return (
    <div className="space-y-4">
      {/* Tiles */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Past proposals" value={files.length} sub={`${files.filter((f) => !f.approved).length} seed files, ${files.filter((f) => f.approved).length} approved in the dashboard`} />
        <Tile label="Paragraphs" value={chunks.length} sub={`${Math.round(chunks.reduce((s, c) => s + (c.words || 0), 0) / 1000)}k words the writer can reuse`} />
        <Tile label="Verticals covered" value={Object.keys(verticalCounts).filter((v) => v !== "networking").length} sub="Enterprise Networking appears in every file as boilerplate" />
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200 bg-white p-3 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpenFile(null); }}
          placeholder="Search any phrase across all proposals (SLA, escalation matrix, Fortinet, P1 response)"
          className="min-w-56 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2 text-[13px] outline-none transition-colors focus:border-emerald-400 dark:border-slate-700 dark:bg-slate-950"
        />
        <select
          value={vertical}
          onChange={(e) => { setVertical(e.target.value); setOpenFile(null); }}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">All verticals</option>
          {Object.entries(verticalCounts).sort((a, b) => b[1] - a[1]).map(([v, n]) => (
            <option key={v} value={v}>{nameOf(v)} ({n})</option>
          ))}
        </select>
        <div className="flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-700">
          {[["proposals", "Proposals"], ["paragraphs", "Paragraphs"]].map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setMode(k)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${mode === k ? "bg-emerald-600 text-white" : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="ml-auto text-[12.5px] text-slate-400">
          {mode === "proposals" ? `Showing ${shown.length} of ${files.length}` : `${paragraphHits.length} matching paragraphs`}
        </span>
      </div>

      {/* Paragraph mode: flat results */}
      {mode === "paragraphs" ? (
        <div className="space-y-2">
          {!ql && <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-[13px] text-slate-400 dark:border-slate-700">Type a phrase to search every paragraph.</p>}
          {paragraphHits.map((c) => (
            <article key={c.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900">
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                {c.client} · {c.section}
              </p>
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-700 dark:text-slate-300">
                <Highlight text={c.text} q={ql} />
              </p>
            </article>
          ))}
        </div>
      ) : (
        /* Proposals mode: split list + reader */
        <div className="grid items-start gap-3.5 lg:grid-cols-[380px_1fr]">
          <ul className="max-h-[70vh] overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
            {shown.map((f) => (
              <li key={f.source}>
                <button
                  type="button"
                  onClick={() => { setOpenFile(f.source === openFile ? null : f.source); setSection(""); }}
                  className={`w-full border-b border-slate-100 px-4 py-3 text-left transition-colors last:border-0 dark:border-slate-800
                    ${openFile === f.source ? "bg-emerald-50 dark:bg-emerald-950" : "hover:bg-slate-50 dark:hover:bg-slate-800"}`}
                >
                  <span className="flex items-center gap-2 text-[13.5px] font-semibold text-slate-900 dark:text-white">
                    {f.client}
                    {f.approved && (
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                        approved in dashboard
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-400">
                    {f.chunks.length} paragraphs · {f.words.toLocaleString()} words
                    {ql && <> · <b className="text-emerald-600">{f.chunks.filter((c) => c.text.toLowerCase().includes(ql)).length} matches</b></>}
                  </span>
                </button>
              </li>
            ))}
            {!shown.length && <li className="p-6 text-center text-[13px] text-slate-400">No proposal matches.</li>}
          </ul>

          <div className="flex max-h-[70vh] min-h-[420px] flex-col rounded-xl border border-slate-200 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
            {!current ? (
              <div className="flex flex-1 flex-col items-center justify-center p-10 text-center text-slate-400">
                <p className="text-[13.5px]">Select a proposal on the left to read it.</p>
              </div>
            ) : (
              <>
                <header className="flex items-start justify-between gap-4 border-b border-slate-200 p-5 dark:border-slate-800">
                  <div className="min-w-0">
                    <h3 className="truncate text-[15px] font-bold text-slate-900 dark:text-white">{current.client}</h3>
                    <p className="truncate text-xs text-slate-400">{current.source}</p>
                  </div>
                  <select
                    value={section}
                    onChange={(e) => setSection(e.target.value)}
                    className="min-w-52 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                  >
                    <option value="">All sections ({currentSections.length})</option>
                    {currentSections.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </header>
                <div className="flex-1 overflow-y-auto px-5 pb-5">
                  {readerChunks.map((c) => (
                    <section key={c.id} className="border-b border-slate-100 py-3.5 last:border-0 dark:border-slate-800">
                      <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">{c.section}</p>
                      <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-slate-700 dark:text-slate-300">
                        <Highlight text={c.text} q={ql} />
                      </p>
                    </section>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
