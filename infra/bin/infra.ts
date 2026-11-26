#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core'
import { CareerAssistantStack } from '../lib/career-assistant-stack'

const app = new cdk.App()

new CareerAssistantStack(app, 'CareerAssistant', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ca-central-1' },
  // `cdk deploy -c modelId=ca.anthropic.claude-haiku-5-5` to switch models
  modelId: app.node.tryGetContext('modelId'),
  description: 'Career Assistant — personal prototype, not affiliated with any employer',
  tags: { project: 'career-assistant-demo' },
})
