"""Regenerate the browser-side copy of the scorer taxonomy so the dashboard
can independently re-verify every score. Run after editing backend/scorer.py:
    python scripts/gen_scorer_js.py > frontend/scorer_data.js
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from scorer import SOLUTIONS, NEGATIVE_KEYWORDS, NETS_VERTICALS, SHORT_KEYWORD_THRESHOLD
sols=[{"id":s["id"],"name":s["name"],"group":s["group"],"weight":s.get("weight",1.0),"keywords":s["keywords"]} for s in SOLUTIONS]
print("/* AUTO-GENERATED from backend/scorer.py. Do not edit by hand; regenerate with scripts/gen_scorer_js.py */")
print("var SCORER_SOLUTIONS="+json.dumps(sols,separators=(',',':'))+";")
print("var SCORER_NEGATIVE="+json.dumps(NEGATIVE_KEYWORDS,separators=(',',':'))+";")
print("var SCORER_VERTICALS="+json.dumps(NETS_VERTICALS,separators=(',',':'))+";")
print("var SCORER_SHORT="+str(SHORT_KEYWORD_THRESHOLD)+";")
