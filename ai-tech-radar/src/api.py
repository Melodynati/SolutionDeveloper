"""One Lambda, two front doors.

A) HTTP API (API Gateway)          GET /rankings?limit=&category=&stage=
                                   GET /tech/{name}
                                   GET /health
B) MCP tool target (Amazon Bedrock AgentCore Gateway, Lambda target).
   The Gateway passes tool arguments as the event and the tool name in
   context.client_context.custom["bedrockAgentCoreToolName"] as "<target>___<tool>".
   Tools: get_top_technologies, get_technology_trend, get_emerging_signals
"""
import json
import os
import urllib.parse

import boto3

S3 = boto3.client("s3")
WEB_BUCKET = os.environ["WEB_BUCKET"]


def _latest():
    return json.loads(S3.get_object(Bucket=WEB_BUCKET, Key="data/latest.json")["Body"].read())


def _slim(r):
    return {k: r[k] for k in ("rank", "tech", "category", "stage", "score", "z", "predicted_change_pct", "is_new")}


# ---- tool implementations (shared by HTTP and MCP) ----
def get_top_technologies(limit=10, category=None, stage=None):
    d = _latest()
    rows = d["rankings"]
    if category:
        rows = [r for r in rows if r["category"].lower() == str(category).lower()]
    if stage:
        rows = [r for r in rows if r["stage"].lower() == str(stage).lower()]
    limit = max(1, min(int(limit or 10), 50))
    return {"generated_at": d["generated_at"], "method": d["method"], "results": [_slim(r) for r in rows[:limit]]}


def get_technology_trend(name):
    d = _latest()
    n = str(name or "").lower()
    match = next((r for r in d["rankings"] if r["tech"].lower() == n), None) or \
        next((r for r in d["rankings"] if n and n in r["tech"].lower()), None)
    if not match:
        return {"error": f"No technology matching '{name}'", "known": [r["tech"] for r in d["rankings"][:30]]}
    return {"generated_at": d["generated_at"], "days": d["days"], **match}


def get_emerging_signals(limit=10):
    d = _latest()
    rows = [r for r in d["rankings"] if r["stage"] in ("Emerging", "Breakout") or r["is_new"]]
    rows.sort(key=lambda r: r["z"], reverse=True)
    return {"generated_at": d["generated_at"], "briefing": d.get("briefing"),
            "results": [_slim(r) for r in rows[:max(1, min(int(limit or 10), 50))]]}


TOOLS = {"get_top_technologies": get_top_technologies,
         "get_technology_trend": get_technology_trend,
         "get_emerging_signals": get_emerging_signals}


def _http(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60"},
            "body": json.dumps(body)}


def handler(event, context):
    # ---- MCP via AgentCore Gateway ----
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    tool_full = custom.get("bedrockAgentCoreToolName")
    if tool_full:
        tool = tool_full.split("___", 1)[-1]
        fn = TOOLS.get(tool)
        if not fn:
            return {"error": f"unknown tool {tool}"}
        args = {k: v for k, v in (event or {}).items() if k in fn.__code__.co_varnames}
        return fn(**args)

    # ---- HTTP API ----
    path = (event or {}).get("rawPath", "/")
    qs = (event or {}).get("queryStringParameters") or {}
    try:
        if path.endswith("/health"):
            return _http(200, {"ok": True})
        if path.endswith("/rankings"):
            return _http(200, get_top_technologies(qs.get("limit", 20), qs.get("category"), qs.get("stage")))
        if "/tech/" in path:
            return _http(200, get_technology_trend(urllib.parse.unquote(path.split("/tech/", 1)[1])))
        return _http(404, {"error": "not found"})
    except S3.exceptions.NoSuchKey:
        return _http(503, {"error": "no rankings yet - run the collector first"})
