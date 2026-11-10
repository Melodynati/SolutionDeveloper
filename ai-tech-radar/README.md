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
- Amazon Bedrock model access for the model in `ModelId` (default `global.anthropic.claude-sonnet-5-5`).
  First-time Anthropic use may require submitting use-case details in the Bedrock console.

## Deploy
```bash
./scripts/deploy.sh ai-tech-radar us-east-1 you@example.com
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
