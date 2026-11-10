#!/usr/bin/env bash
# One-command deploy for the AI Tech Radar lab.
# Usage: ./scripts/deploy.sh [stack-name] [region] [alert-email]
set -euo pipefail
STACK=${1:-ai-tech-radar}
REGION=${2:-us-east-1}
EMAIL=${3:-}
cd "$(dirname "$0")/.."

echo "==> Running unit tests"
python3 tests/test_logic.py

echo "==> Building"
sam build --region "$REGION"

echo "==> Deploying stack $STACK to $REGION"
sam deploy --stack-name "$STACK" --region "$REGION" --resolve-s3 \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides AlertEmail="$EMAIL"

out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
WEB=$(out WebBucketName); COLLECTOR=$(out CollectorFunctionName)

echo "==> Uploading dashboard"
python3 scripts/make_sample.py
aws s3 sync dashboard/ "s3://$WEB/" --region "$REGION" --exclude "data/latest.json"

echo "==> Seeding 5 days of history (backfill) - takes a few minutes"
aws lambda invoke --function-name "$COLLECTOR" --region "$REGION" \
  --cli-binary-format raw-in-base64-out --payload '{"backfill_days":5}' \
  --cli-read-timeout 900 /dev/stdout | head -c 2000; echo

echo "==> First live collection"
aws lambda invoke --function-name "$COLLECTOR" --region "$REGION" \
  --cli-binary-format raw-in-base64-out --payload '{}' --cli-read-timeout 900 /dev/stdout | head -c 2000; echo

echo
echo "Dashboard : $(out DashboardUrl)   (CloudFront may take ~5 min on first deploy)"
echo "API       : $(out ApiUrl)/rankings"
echo "MCP target: $(out ApiFunctionArn)   (use in AgentCore Gateway, Module 6)"
