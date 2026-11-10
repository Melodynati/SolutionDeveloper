"""Ranker Lambda — invoked by the collector after each run.

Builds 14-day daily series per technology, ranks + forecasts, writes:
  s3://<web bucket>/data/latest.json                (dashboard + API read this)
  s3://<raw bucket>/rankings/dt=YYYY-MM-DD/HH.json  (history for back-testing)
Publishes an SNS alert when a technology newly enters Breakout or Emerging.
Optionally asks Bedrock for a short analyst briefing on the movers.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3

import store
from scoring import rank

S3 = boto3.client("s3")
SNS = boto3.client("sns")
WEB_BUCKET = os.environ["WEB_BUCKET"]
RAW_BUCKET = os.environ["RAW_BUCKET"]
TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
ENABLE_BRIEFING = os.environ.get("ENABLE_BRIEFING", "true").lower() == "true"
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-5-5")
DAYS = 14
LATEST_KEY = "data/latest.json"


def _previous_stages():
    try:
        prev = json.loads(S3.get_object(Bucket=WEB_BUCKET, Key=LATEST_KEY)["Body"].read())
        return {r["tech"]: r["stage"] for r in prev.get("rankings", [])}
    except Exception:
        return {}


def _briefing(rows):
    movers = [r for r in rows if r["stage"] in ("Breakout", "Emerging", "Rising")][:12]
    if not movers:
        return None
    facts = [{k: r[k] for k in ("tech", "category", "stage", "score", "z", "predicted_change_pct", "is_new")} for r in movers]
    prompt = ("You are an AI technology analyst. Using ONLY these computed signals, write a 120-word briefing for "
              "a solution developer: what is accelerating, what to learn or pilot first, and one caution. "
              "Do not invent numbers.\n" + json.dumps(facts))
    try:
        r = boto3.client("bedrock-runtime").converse(
            modelId=MODEL_ID, messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.2})
        return r["output"]["message"]["content"][0]["text"]
    except Exception as e:
        print(json.dumps({"level": "WARN", "msg": "briefing_failed", "error": str(e)[:200]}))
        return None


def handler(event, context):
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=DAYS - 1)).date()
    day_index = {(start_day + timedelta(days=i)).isoformat(): i for i in range(DAYS)}
    since_key = f"{start_day.isoformat()}T00"
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H")

    reg = store.registry()
    series, srcs = {}, defaultdict(set)
    for tech in reg:
        daily = [0.0] * DAYS
        for it in store.hourly(tech, since_key):
            hk = it["sk"][2:]
            i = day_index.get(hk[:10])
            if i is not None:
                daily[i] += float(it.get("signal", 0))
                if hk >= week_ago:
                    srcs[tech].update(it.get("sources", set()))
        series[tech] = daily

    rows = rank(series, srcs, reg)
    prev = _previous_stages()
    alerts = [r for r in rows if r["stage"] in ("Breakout", "Emerging") and prev.get(r["tech"]) != r["stage"]]

    doc = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": DAYS,
        "days": [(start_day + timedelta(days=i)).isoformat() for i in range(DAYS)],
        "method": "score = 45% volume + 35% momentum (z-score, last day vs prior 6) + 20% source diversity; "
                  "forecast = Holt damped-trend smoothing, 7 days",
        "rankings": rows,
        "new_alerts": [r["tech"] for r in alerts],
        "briefing": _briefing(rows) if ENABLE_BRIEFING else None,
    }
    body = json.dumps(doc).encode()
    S3.put_object(Bucket=WEB_BUCKET, Key=LATEST_KEY, Body=body, ContentType="application/json",
                  CacheControl="max-age=60")
    S3.put_object(Bucket=RAW_BUCKET, Key=f"rankings/dt={now:%Y-%m-%d}/{now:%H}.json", Body=body,
                  ContentType="application/json")

    if alerts and TOPIC_ARN:
        lines = [f"{r['stage'].upper()}: {r['tech']} (score {r['score']}, z {r['z']}, "
                 f"7-day forecast {r['predicted_change_pct']:+}%)" for r in alerts[:10]]
        SNS.publish(TopicArn=TOPIC_ARN, Subject="AI Tech Radar: new movers",
                    Message="\n".join(lines) + ("\n\n" + doc["briefing"] if doc["briefing"] else ""))

    print(json.dumps({"level": "INFO", "msg": "rank_done", "techs": len(rows), "alerts": doc["new_alerts"]}))
    return {"techs": len(rows), "alerts": doc["new_alerts"]}
