"""Public-internet signal collectors. Standard library only (no dependencies).

Every collector returns a list of "signal items":
    {"source": str, "id": str, "title": str, "text": str, "url": str,
     "engagement": float, "published": iso8601 str}

Sources (all public, no login):
  - Hacker News via the Algolia HN Search API   -> developer attention
  - GitHub Search API (new AI repos, by stars)  -> builder adoption
  - arXiv API (cs.AI / cs.LG / cs.CL newest)    -> research pipeline (earliest signal)
  - Hugging Face Hub API (trendingScore)        -> open-model momentum

Each collector is isolated: one source failing never stops the others.
"""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

USER_AGENT = os.environ.get("USER_AGENT", "ai-tech-radar-lab/1.0 (educational sandbox)")
TIMEOUT = 15


def _get(url, headers=None, raw=False):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read()
    return body if raw else json.loads(body)


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Algolia (HN search) has no OR operator in the query string: "AI OR LLM" would require every
# word, including "OR". So we run one single-term query per keyword and merge by story ID.
HN_TERMS = ["AI", "LLM", "GPT", "agent", "model", "Claude", "MCP"]

# GitHub search does not allow OR between qualifiers such as topic: (HTTP 422), so one query per topic.
GH_TOPICS = ["llm", "ai-agents", "generative-ai", "mcp"]


def hn_search(start_ts, stop_ts=None, per_term=100):
    """Hacker News stories created in (start_ts, stop_ts], merged across HN_TERMS."""
    window = f"created_at_i>{start_ts}" + (f",created_at_i<={stop_ts}" if stop_ts else "")
    seen, out = set(), []
    for term in HN_TERMS:
        q = urllib.parse.urlencode({"query": term, "tags": "story",
                                    "numericFilters": window, "hitsPerPage": per_term})
        data = _get(f"https://hn.algolia.com/api/v1/search_by_date?{q}")
        for h in data.get("hits", []):
            oid = h.get("objectID")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            title = h.get("title") or ""
            out.append({
                "source": "hackernews",
                "id": f"hn:{oid}",
                "title": title,
                "text": title,
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "engagement": float((h.get("points") or 0) + 2 * (h.get("num_comments") or 0)),
                "published": h.get("created_at"),
            })
    return out


def collect_hackernews(since_hours=2, per_term=50):
    since = int((datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp())
    return hn_search(since, per_term=per_term)


def collect_github(days=7, per_topic=25):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")  # optional: raises rate limit from 10 to 30 search req/min
    if token:
        headers["Authorization"] = f"Bearer {token}"
    seen, out = set(), []
    for topic in GH_TOPICS:
        params = urllib.parse.urlencode({"q": f"created:>{since} topic:{topic}", "sort": "stars",
                                         "order": "desc", "per_page": per_topic})
        data = _get(f"https://api.github.com/search/repositories?{params}", headers=headers)
        for r in data.get("items", []):
            name = r.get("full_name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            topics = " ".join(r.get("topics") or [])
            out.append({
                "source": "github",
                "id": f"gh:{name}",
                "title": name,
                "text": f"{name} {r.get('description') or ''} {topics}",
                "url": r.get("html_url"),
                "engagement": float(r.get("stargazers_count") or 0),
                "published": r.get("created_at"),
            })
    return out


def collect_arxiv(limit=60):
    q = urllib.parse.urlencode({
        "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
        "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": limit,
    })
    body = _get(f"https://export.arxiv.org/api/query?{q}", headers={"Accept": "application/atom+xml"}, raw=True)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(body)
    out = []
    for e in root.findall("a:entry", ns):
        title = re.sub(r"\s+", " ", (e.findtext("a:title", "", ns) or "")).strip()
        summary = re.sub(r"\s+", " ", (e.findtext("a:summary", "", ns) or "")).strip()
        aid = (e.findtext("a:id", "", ns) or "").rsplit("/", 1)[-1]
        out.append({
            "source": "arxiv",
            "id": f"arxiv:{aid}",
            "title": title,
            "text": f"{title}. {summary[:400]}",
            "url": e.findtext("a:id", "", ns),
            "engagement": 1.0,  # papers carry no engagement signal at publish time
            "published": e.findtext("a:published", "", ns),
        })
    return out


def collect_huggingface(limit=50):
    params = [("sort", "trendingScore"), ("direction", "-1"), ("limit", str(limit))]
    for f in ("downloads", "likes", "trendingScore", "pipeline_tag", "tags", "createdAt"):
        params.append(("expand[]", f))
    data = _get("https://huggingface.co/api/models?" + urllib.parse.urlencode(params))
    out = []
    for m in data:
        mid = m.get("id") or m.get("modelId")
        tags = " ".join(t for t in (m.get("tags") or []) if ":" not in t)
        out.append({
            "source": "huggingface",
            "id": f"hf:{mid}",
            "title": mid,
            "text": f"{mid} {m.get('pipeline_tag') or ''} {tags}",
            "url": f"https://huggingface.co/{mid}",
            "engagement": float(m.get("trendingScore") or m.get("likes") or 0),
            "published": m.get("createdAt"),
        })
    return out


COLLECTORS = {
    "hackernews": collect_hackernews,
    "github": collect_github,
    "arxiv": collect_arxiv,
    "huggingface": collect_huggingface,
}


def collect_all(enabled=None):
    """Run every enabled collector; return (items, per-source status)."""
    enabled = enabled or list(COLLECTORS)
    items, status = [], {}
    for name in enabled:
        try:
            got = COLLECTORS[name]()
            items.extend(got)
            status[name] = {"ok": True, "count": len(got)}
        except Exception as e:  # isolate failures per source
            status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    return items, status
