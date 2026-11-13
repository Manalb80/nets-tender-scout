import snapshot from "../../../data/pipeline_snapshot.json";

/**
 * GET /api/pipeline
 * The pipeline API the production frontend consumes.
 *
 * Today it serves the committed snapshot (exported from the artifact DB under
 * the dashboard's own live-tender rule). At backend cut-over, this handler
 * swaps its source for Firestore's pipeline/ collection (see backend/manager.py)
 * with no change to consumers: same shape, {meta, tenders}.
 *
 * Query params:
 *   portal=PPRA|EPADS|Sindh Bank   filter by source portal
 *   days=N                         only tenders closing within N days
 */
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const portal = searchParams.get("portal");
  const days = parseInt(searchParams.get("days") || "", 10);

  let tenders = snapshot.tenders;
  if (portal) tenders = tenders.filter((t) => t.source === portal);
  if (!Number.isNaN(days)) tenders = tenders.filter((t) => t.days <= days);

  return Response.json(
    { meta: { ...snapshot.meta, filtered: tenders.length }, tenders },
    { headers: { "Cache-Control": "public, max-age=300" } }
  );
}
