# Infrastructure (AWS CDK, TypeScript)

Stack `CareerAssistant` en `ca-central-1` : DynamoDB, Guardrail Bedrock, Knowledge Base sur S3 Vectors,
Lambda FastAPI, API Gateway HTTP, S3 + CloudFront. Voir le [README principal](../README.md).

```bash
npm install
npm test                      # assertions sur le template (TTL, throttling, Guardrail, S3 Vectors…)
npx cdk synth
npx cdk deploy CareerAssistant
npx cdk destroy CareerAssistant
```

Code de la stack : [lib/career-assistant-stack.ts](lib/career-assistant-stack.ts).
