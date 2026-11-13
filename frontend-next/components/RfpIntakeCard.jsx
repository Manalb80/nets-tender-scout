"use client";

/**
 * Step 1: RFP Intake & SharePoint Cloud Folder Card
 * Production component for the NETS Presales Next.js frontend.
 *
 * Design: Flowbite/Tailwind idiom, Tesla/Linear minimalist aesthetic.
 * - No external CDN scripts; all interactivity is local React state.
 * - No hardcoded paths; the SharePoint base comes from an env var or prop.
 * - Dark mode via Tailwind `dark:` classes (class strategy).
 *
 * Usage:
 *   <RfpIntakeCard
 *     tender={{
 *       id: "PPRA-TS0000017630E",
 *       title: "Generator and UPS for Regional Office",
 *       portal: "PPRA EPMS",
 *       detailUrl: "https://epms.ppra.gov.pk/public/tenders/tender-details/TS0000017630E",
 *       acqStatus: "PENDING",           // PENDING | AUTO_DOWNLOADED | MANUAL_DOWNLOAD_REQUIRED | OCR_PROCESSED
 *       docs: [{ name: "RFP.pdf", pages: 42 }],
 *       hasText: false,
 *     }}
 *     onUpload={(files) => ...}
 *   />
 *
 * Env (.env.local):
 *   NEXT_PUBLIC_SHAREPOINT_BASE=https://netsinternational-my.sharepoint.com/personal/iqra_iqbal_nets-international_com/Documents/NETS-Karachi%20Presales-Technical%20Proposals
 */

import { useRef, useState } from "react";

const SP_BASE =
  process.env.NEXT_PUBLIC_SHAREPOINT_BASE ||
  "https://netsinternational-my.sharepoint.com/personal/iqra_iqbal_nets-international_com/Documents/NETS-Karachi%20Presales-Technical%20Proposals";

/* ── Status chip: one vocabulary for acquisition states ── */
const STATUS = {
  PENDING: { label: "No document yet", cls: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700" },
  AUTO_DOWNLOADED: { label: "Files detected", cls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800" },
  AUTO_DOWNLOADED_HEADLESS: { label: "Fetched via browser", cls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800" },
  OCR_PROCESSED: { label: "Scanned PDF, OCR applied", cls: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800" },
  MANUAL_DOWNLOAD_REQUIRED: { label: "Portal needs a login", cls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800" },
  IN_HAND: { label: "Document in hand", cls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800" },
};

function StatusChip({ status }) {
  const s = STATUS[status] || STATUS.PENDING;
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${s.cls}`}>
      {s.label}
    </span>
  );
}

/* ── Icons: inline SVG, no icon-font CDN ── */
const FolderIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
);
const GlobeIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);
const LinkIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
);
const UploadIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);
const CheckIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

/* ── Copy-to-clipboard button with visual feedback ── */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable (http, permissions): select-fallback could go here */
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-live="polite"
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors
        ${copied
          ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          : "border-slate-200 bg-white text-slate-700 hover:border-emerald-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-emerald-600"}`}
    >
      {copied ? (<><CheckIcon className="h-3.5 w-3.5" /> Copied</>) : "Copy"}
    </button>
  );
}

/* ── The card ── */
export default function RfpIntakeCard({ tender, onUpload, sharePointBase = SP_BASE }) {
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  const status = tender?.hasText ? "IN_HAND" : tender?.acqStatus || "PENDING";
  const folderUrl =
    tender?.sharepointFolderUrl || `${sharePointBase}/${encodeURIComponent(tender?.id ?? "")}`;
  const folderConfirmed = Boolean(tender?.sharepointConfirmed);
  /* The per-tender subfolder 404s until provisioned; open the base until confirmed. */
  const openUrl = folderConfirmed ? folderUrl : sharePointBase;

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length || !onUpload) return;
    setUploading(true);
    try {
      await onUpload(files);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {/* Header */}
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">Step 1</p>
          <h2 className="mt-0.5 text-lg font-bold text-slate-900 dark:text-white">RFP document</h2>
        </div>
        <StatusChip status={status} />
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        {/* Left: upload */}
        <div className="lg:col-span-3">
          {tender?.docs?.length ? (
            <ul className="mb-4 space-y-1.5">
              {tender.docs.map((d) => (
                <li
                  key={d.name}
                  className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800"
                >
                  <span className="font-medium text-slate-900 dark:text-white">{d.name}</span>
                  {d.pages ? (
                    <span className="text-xs text-slate-500 dark:text-slate-400">{d.pages} pages</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-4 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
              Upload every PDF in the tender folder: RFP, annexes, corrigenda, BOQ sheets. The text is
              extracted server-side and the Step 2 analyses start automatically.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2.5">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 focus-within:ring-4 focus-within:ring-emerald-200 dark:focus-within:ring-emerald-900">
              <UploadIcon className="h-4 w-4" />
              {uploading ? "Reading PDFs..." : tender?.hasText ? "Add or replace PDFs" : "Upload RFP PDFs"}
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                multiple
                className="sr-only"
                onChange={handleFiles}
                disabled={uploading}
              />
            </label>

            <a
              href={tender?.detailUrl || "#"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-emerald-600 dark:hover:text-emerald-300"
            >
              <GlobeIcon className="h-4 w-4" />
              Download the RFP on {tender?.portal ?? "the portal"}
            </a>
          </div>
        </div>

        {/* Right: SharePoint cloud folder */}
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 dark:border-slate-800 dark:bg-slate-950 lg:col-span-2">
          <div className="mb-4 flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-400">
              <FolderIcon className="h-4.5 w-4.5" />
            </span>
            <div>
              <p className="text-sm font-bold text-slate-900 dark:text-white">Cloud Folder</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Corporate SharePoint</p>
            </div>
          </div>

          {/* Path row: truncated, with copy feedback */}
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900">
            <LinkIcon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <span
              title={folderUrl}
              className="min-w-0 flex-1 truncate font-mono text-xs text-slate-600 dark:text-slate-300"
            >
              {folderUrl}
            </span>
            <CopyButton text={folderUrl} />
          </div>

          <a
            href={openUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700"
          >
            <FolderIcon className="h-4 w-4" />
            Open shared folder
          </a>

          {!folderConfirmed && (
            <p className="mt-2 text-center text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
              Opens the proposals folder. Create or open the subfolder{" "}
              <span className="font-semibold text-slate-600 dark:text-slate-300">{tender?.id}</span> for
              this tender&apos;s files.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
