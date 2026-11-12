"""Collector Lambda — runs hourly from EventBridge Scheduler.

1. Pull signals from public sources (isolated per source)
2. Drop items already counted (DynamoDB conditional put)
3. Classify new items into AI technologies with Bedrock (keyword fallback)
4. Write raw evidence to S3 (audit trail) and add signal to hourly buckets
5. Invoke the ranker asynchronously

Manual test event:  {}                     normal run
Backfill event:     {"backfill_days": 7}   seeds history from Hacker News + arXiv so day-1 trends exist
"""
import gzip
import json
import os
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone

import boto3

import sources
import store
from extract import extract
from scoring import item_signal
from taxonomy import category_of

S3 = boto3.client("s3")
LAMBDA = boto3.client("lambda")
CW = boto3.client("cloudwatch")
RAW_BUCKET = os.environ["RAW_BUCKET"]
RANKER_FN = os.environ.get("RANKER_FUNCTION", "")
USE_BEDROCK = os.environ.get("USE_BEDROCK", "true").lower() == "true"
# Sources whose items carry a real publish time get bucketed by publish hour;
# snapshot sources (GitHub stars, HF trending) are bucketed by collection hour.
PUBLISH_TIME_SOURCES = {"hackernews", "arxiv"}


def _hour_key(it, now):
    if it["source"] in PUBLISH_TIME_SOURCES and it.get("published"):
        try:
            dt = datetime.fromisoformat(it["published"].replace("Z", "+00:00"))
            if now - dt < timedelta(days=15):
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
        except ValueError:
            pass
    return now.strftime("%Y-%m-%dT%H")


def _backfill_items(days):
    """Hacker News day-by-day windows + a large arXiv page."""
    items = []
    end = datetime.now(timezone.utc)
    for d in range(days, 0, -1):
        start_ts = int((end - timedelta(days=d)).timestamp())
        stop_ts = int((end - timedelta(days=d - 1)).timestamp())
        try:
            items.extend(sources.hn_search(start_ts, stop_ts, per_term=100))
        except Exception as e:
            print(json.dumps({"level": "WARN", "msg": "backfill_hn_failed", "day": d, "error": str(e)[:200]}))
    try:
        items.extend(sources.collect_arxiv(limit=300))
    except Exception as e:
        print(json.dumps({"level": "WARN", "msg": "backfill_arxiv_failed", "error": str(e)[:200]}))
    return items


def handler(event, context):
    now = datetime.now(timezone.utc)
    event = event or {}
    if event.get("backfill_days"):
        items, status = _backfill_items(int(event["backfill_days"])), {"backfill": True}
    else:
        items, status = sources.collect_all()

    fresh = [it for it in items if store.mark_seen(it["id"])]
    fresh, xstats = extract(fresh, use_bedrock=USE_BEDROCK)

    per_tech = Counter()
    for it in fresh:
        hk = _hour_key(it, now)
        sig = item_signal(it["source"], it["engagement"])
        for t in it["techs"]:
            store.add_signal(t, hk, sig, it["source"])
            store.register(t, category_of(t), False)
            per_tech[t] += 1
        for t in it["new_techs"]:
            store.add_signal(t, hk, sig, it["source"])
            store.register(t, "Emerging / Uncategorised", True)
            per_tech[t] += 1

    # Raw evidence for audit / reprocessing (gzip JSON Lines, partitioned by hour)
    if fresh:
        key = f"raw/dt={now:%Y-%m-%d}/hour={now:%H}/{context.aws_request_id if context else 'local'}.jsonl.gz"
        body = gzip.compress("\n".join(json.dumps(i, default=str) for i in fresh).encode())
        S3.put_object(Bucket=RAW_BUCKET, Key=key, Body=body, ContentType="application/json", ContentEncoding="gzip")

    CW.put_metric_data(Namespace="AITechRadar", MetricData=[
        {"MetricName": "ItemsCollected", "Value": len(items), "Unit": "Count"},
        {"MetricName": "ItemsNew", "Value": len(fresh), "Unit": "Count"},
        {"MetricName": "BedrockInputTokens", "Value": xstats["input_tokens"], "Unit": "Count"},
        {"MetricName": "BedrockOutputTokens", "Value": xstats["output_tokens"], "Unit": "Count"},
        {"MetricName": "ExtractFallbackBatches", "Value": xstats["fallback_batches"], "Unit": "Count"},
        {"MetricName": "SourcesFailed", "Unit": "Count",
         "Value": sum(1 for s in status.values() if isinstance(s, dict) and not s.get("ok", True))},
    ])

    if RANKER_FN:
        LAMBDA.invoke(FunctionName=RANKER_FN, InvocationType="Event", Payload=b"{}")

    summary = {"collected": len(items), "new": len(fresh), "sources": status,
               "extract": xstats, "top_mentions": per_tech.most_common(10)}
    print(json.dumps({"level": "INFO", "msg": "collect_done", **summary}, default=str))
    return summary
