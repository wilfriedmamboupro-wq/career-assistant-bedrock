import * as cdk from 'aws-cdk-lib/core'
import { Match, Template } from 'aws-cdk-lib/assertions'
import { CareerAssistantStack } from '../lib/career-assistant-stack'

// Synthesizing bundles the Lambda locally (pip) and needs frontend/dist to exist.
const template = Template.fromStack(
  new CareerAssistantStack(new cdk.App(), 'Test', {
    env: { account: '111111111111', region: 'ca-central-1' },
  }),
)

test('sessions expire through DynamoDB TTL', () => {
  template.hasResourceProperties('AWS::DynamoDB::GlobalTable', {
    TimeToLiveSpecification: { AttributeName: 'ttl', Enabled: true },
  })
})

test('API is throttled', () => {
  template.hasResourceProperties('AWS::ApiGatewayV2::Stage', {
    DefaultRouteSettings: { ThrottlingRateLimit: 5, ThrottlingBurstLimit: 10 },
  })
})

test('guardrail anonymizes Canadian SIN and blocks candidate evaluation', () => {
  template.hasResourceProperties('AWS::Bedrock::Guardrail', {
    SensitiveInformationPolicyConfig: {
      PiiEntitiesConfig: Match.arrayWith([
        Match.objectLike({ Type: 'CA_SOCIAL_INSURANCE_NUMBER', InputAction: 'ANONYMIZE' }),
      ]),
    },
    TopicPolicyConfig: {
      TopicsConfig: Match.arrayWith([Match.objectLike({ Name: 'CandidateEvaluation', Type: 'DENY' })]),
    },
  })
})

test('guardrail is multilingual (STANDARD tier) and stays in Canada', () => {
  template.hasResourceProperties('AWS::Bedrock::Guardrail', {
    CrossRegionConfig: { GuardrailProfileArn: Match.stringLikeRegexp('guardrail-profile/ca\\.guardrail') },
    TopicPolicyConfig: { TopicsTierConfig: { TierName: 'STANDARD' } },
    SensitiveInformationPolicyConfig: {
      PiiEntitiesConfig: Match.arrayWith([
        Match.objectLike({ Type: 'EMAIL', InputAction: 'ANONYMIZE', InputEnabled: true }),
      ]),
    },
  })
})

test('knowledge base uses S3 Vectors (no OpenSearch Serverless)', () => {
  template.hasResourceProperties('AWS::Bedrock::KnowledgeBase', {
    StorageConfiguration: { Type: 'S3_VECTORS' },
  })
  template.resourceCountIs('AWS::OpenSearchServerless::Collection', 0)
})

test('Lambda uses the Canada-only Nova Lite profile by default and keeps logs 7 days', () => {
  template.hasResourceProperties('AWS::Lambda::Function', {
    Environment: { Variables: Match.objectLike({ CA_MODEL_ID: 'ca.amazon.nova-lite-v1:0', CA_MODE: 'aws' }) },
  })
  template.hasResourceProperties('AWS::Logs::LogGroup', { RetentionInDays: 7 })
})

test('website bucket is private (CloudFront OAC only)', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    PublicAccessBlockConfiguration: Match.objectLike({ BlockPublicAcls: true, RestrictPublicBuckets: true }),
  })
})
