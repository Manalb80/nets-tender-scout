import KnowledgeBankBrowser from "../../components/KnowledgeBankBrowser";
import chunks from "../../../scripts/kb/out/kb_chunks.json";
import solutionNames from "../../data/solution_names.json";

export const metadata = { title: "Knowledge bank · NETS Presales" };

/**
 * Knowledge bank, wired to the real corpus.
 * Data source: scripts/kb/out/kb_chunks.json, the same build_kb.py output the
 * artifact serves as an asset. Agent 6 approvals land in the kb_live collection;
 * in production this page swaps the static import for the API route that merges
 * seed chunks with kb_live (see backend/manager.py notes).
 */
export default function KnowledgePage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
          Knowledge bank
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Every past proposal the writer can draw on. Read-only; new proposals arrive through
          Agent 6 when an architect approves one.
        </p>
      </div>
      <KnowledgeBankBrowser chunks={chunks} solutionNames={solutionNames} />
    </div>
  );
}
