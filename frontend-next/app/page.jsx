export default function Home() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
        Production frontend
      </h1>
      <p className="max-w-xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
        This is the Next.js twin of the Pre-Sales NETS Enterprise Solution artifact. Views are
        ported one at a time; the live dashboard remains the artifact until cut-over.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <a
          href="/knowledge"
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-card transition-colors hover:border-brand dark:border-slate-800 dark:bg-slate-900"
        >
          <p className="text-[15px] font-bold text-slate-900 dark:text-white">Knowledge bank</p>
          <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
            Browse and search every past NETS proposal the writer draws on. Live now.
          </p>
        </a>
        <div className="rounded-xl border border-dashed border-slate-200 p-6 dark:border-slate-700">
          <p className="text-[15px] font-bold text-slate-400">Leadership, Workbench, Bid board</p>
          <p className="mt-1 text-[13px] text-slate-400">Next in the port order.</p>
        </div>
      </div>
    </div>
  );
}
