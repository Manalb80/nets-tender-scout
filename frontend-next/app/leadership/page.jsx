import CommandCentre from "../../components/CommandCentre";
import snapshot from "../../data/pipeline_snapshot.json";

export const metadata = { title: "Leadership Command Centre · NETS Presales" };

/**
 * Leadership Command Centre: dark high-density executive view, one scroll,
 * running on a real snapshot of the dashboard DB (data/pipeline_snapshot.json,
 * the live qualified set under the same rule the artifact uses). The pipeline
 * API replaces the static import at cut-over. The previous light overview
 * remains available as components/LeadershipOverview.jsx.
 */
export default function LeadershipPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
          Leadership Command Centre
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {snapshot.meta.qualified_open} live qualified tenders across PPRA EPMS, EPADS and Sindh Bank, one scroll: macro, funnel, blockers, register.
        </p>
      </div>
      <CommandCentre tenders={snapshot.tenders} exportedAt={snapshot.meta.exported_at} />
    </div>
  );
}
