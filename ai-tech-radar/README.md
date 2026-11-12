# AI Tech Radar — AWS sandbox lab

Ranks AI technologies by momentum from public internet signals and forecasts the next 7 days.
Serverless, ~15 minutes to deploy, runs hourly on its own.

```
EventBridge Scheduler (hourly) ─▶ Collector Lambda ─┬─▶ Hacker News / GitHub / arXiv / Hugging Face (public APIs)
                                                    ├─▶ Amazon Bedrock (classify items → technologies, forced tool use)
                                                    ├─▶ DynamoDB (dedupe + hourly signal buckets)
                                                    ├─▶ S3 raw/ (evidence, audit)
                                                    └─▶ Ranker Lambda ─▶ score + damped-Holt forecast + Bedrock briefing
                                                                        ├─▶ S3 data/latest.json ─▶ CloudFront ─▶ Dashboard
                                                                        └─▶ SNS alert on new Breakout / Emerging
API Gateway (HTTP) ─┐
AgentCore Gateway  ─┴─▶ API Lambda (REST + 3 MCP tools)
```

## Prerequisites
- AWS account with admin (sandbox) access, AWS CLI v2, AWS SAM CLI, Python 3.13
- Optional: Amazon Bedrock quota for the model in `ModelId` (default `global.amazon.nova-2-lite-v1:0`).
  The stack deploys with `UseBedrock=false` (keyword mode) by default, because new AWS accounts often
  start with zero Bedrock quota. Everything except AI labels and the briefing works in keyword mode.
  No laptop install? Run everything from AWS CloudShell (AWS CLI, SAM CLI, git and Python 3.13 are built in).

## Deploy
```bash
./scripts/deploy.sh ai-tech-radar ap-southeast-2 you@example.com false   # keyword mode (AI off)
./scripts/deploy.sh ai-tech-radar ap-southeast-2 you@example.com true    # later, once Bedrock works
```
Then confirm the SNS subscription email and open the `DashboardUrl` output.

## Files
| Path | What it is |
|---|---|
| `template.yaml` | All infrastructure (SAM / CloudFormation) |
| `src/sources.py` | Public-source collectors (standard library only) |
| `src/extract.py` | Bedrock classification with schema-forced tool use + keyword fallback |
| `src/scoring.py` | Pure ranking + forecasting math (unit-tested) |
| `src/collector.py`, `src/ranker.py`, `src/api.py` | The three Lambda handlers |
| `src/taxonomy.py` | Seed list of 32 AI technologies — edit to fit your market |
| `dashboard/index.html` | Static dashboard (light/dark, mobile) |
| `mcp/tool-schema.json` | Tool definitions for the AgentCore Gateway Lambda target |
| `tests/test_logic.py` | Offline unit tests |

## Tear down
```bash
aws s3 rm s3://<WebBucketName> --recursive
aws s3api delete-objects ... # RawBucket is versioned: empty all versions, or use the console "Empty" button
sam delete --stack-name ai-tech-radar
```

The full lab guide (modules, validation checklist, architecture decisions, PoD, pitch, vendor questions) is the companion document.
