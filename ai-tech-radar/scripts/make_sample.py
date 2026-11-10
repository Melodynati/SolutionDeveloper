"""Generate dashboard/data/sample.json (illustrative demo data, NOT real measurements).

Lets you preview the dashboard before the pipeline has run. Uses the real scoring code.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from scoring import rank  # noqa: E402
from taxonomy import TAXONOMY, category_of  # noqa: E402

random.seed(7)
DAYS = 14
series, srcs, meta = {}, {}, {}
profiles = {"rise": lambda d: 1 + d * 0.12, "spike": lambda d: 1 if d < 13 else 3.2,
            "fall": lambda d: 1.6 - d * 0.07, "flat": lambda d: 1.0}
for i, tech in enumerate(TAXONOMY):
    base = random.uniform(2, 40)
    prof = random.choice(list(profiles))
    series[tech] = [max(0.0, base * profiles[prof](d) * random.uniform(0.85, 1.15)) for d in range(DAYS)]
    srcs[tech] = set(random.sample(["arxiv", "github", "hackernews", "huggingface"], random.randint(1, 4)))
    meta[tech] = {"category": category_of(tech), "is_new": False}
for name in ["Test-time training", "Agent memory layers"]:
    series[name] = [0.0] * 10 + [0.5, 1.0, 1.4, 4.5]
    srcs[name] = {"arxiv", "github"}
    meta[name] = {"category": "Emerging / Uncategorised", "is_new": True}

now = datetime.now(timezone.utc)
start = (now - timedelta(days=DAYS - 1)).date()
doc = {
    "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "window_days": DAYS,
    "days": [(start + timedelta(days=i)).isoformat() for i in range(DAYS)],
    "method": "score = 45% volume + 35% momentum (z-score, last day vs prior 6) + 20% source diversity; "
              "forecast = Holt damped-trend smoothing, 7 days",
    "rankings": rank(series, srcs, meta),
    "new_alerts": [],
    "briefing": "DEMO DATA - illustrative only. Real briefings are written by Amazon Bedrock from live signals.",
}
os.makedirs(os.path.join(ROOT, "dashboard", "data"), exist_ok=True)
with open(os.path.join(ROOT, "dashboard", "data", "sample.json"), "w") as f:
    json.dump(doc, f)
print("wrote dashboard/data/sample.json with", len(doc["rankings"]), "technologies")
