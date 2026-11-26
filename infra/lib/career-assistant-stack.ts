import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import * as cdk from 'aws-cdk-lib/core'
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2'
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations'
import * as bedrock from 'aws-cdk-lib/aws-bedrock'
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront'
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins'
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb'
import * as iam from 'aws-cdk-lib/aws-iam'
import * as lambda from 'aws-cdk-lib/aws-lambda'
import * as logs from 'aws-cdk-lib/aws-logs'
import * as s3 from 'aws-cdk-lib/aws-s3'
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment'
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors'
import * as cr from 'aws-cdk-lib/custom-resources'
import { Construct } from 'constructs'

const ROOT = join(__dirname, '..', '..')
const BACKEND = join(ROOT, 'backend')
const FRONTEND_DIST = join(ROOT, 'frontend', 'dist')
const KB_DIR = join(BACKEND, 'data', 'kb')

// Canada-only inference profiles: inference stays in Canadian regions.
const MODELS = {
  'ca.amazon.nova-lite-v1:0': 'amazon.nova-lite-v1:0', // default, cheapest
  'ca.anthropic.claude-haiku-5-5': 'anthropic.claude-haiku-5-5', // quality option
} as const
// Amazon-owned (no Marketplace subscription), multilingual incl. French, 1024 dimensions
const EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0'
const EMBEDDING_DIMENSIONS = 1024
const GUARDRAIL_PROFILE = 'ca.guardrail.v1:0'
const GUARDRAIL_PROFILE_ARN = (stack: cdk.Stack) =>
  `arn:aws:bedrock:${stack.region}:${stack.account}:guardrail-profile/${GUARDRAIL_PROFILE}`

export interface CareerAssistantProps extends cdk.StackProps {
  /** Inference profile used by the chat Lambda (switch without code change). */
  modelId?: keyof typeof MODELS
}

export class CareerAssistantStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CareerAssistantProps = {}) {
    super(scope, id, props)
    const modelId = props.modelId ?? 'ca.amazon.nova-lite-v1:0'
    const demo = { removalPolicy: cdk.RemovalPolicy.DESTROY } // whole demo goes with `cdk destroy`

    // ---------- Sessions + recruiter tickets (expire after 7 days) ----------
    const table = new dynamodb.TableV2(this, 'Table', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      billing: dynamodb.Billing.onDemand(),
      timeToLiveAttribute: 'ttl',
      ...demo,
    })

    // ---------- Guardrail: PII masking, denied topics, prompt attacks ----------
    // STANDARD tier = multilingual (the CLASSIC tier only understands English). It requires a
    // cross-region guardrail profile: the Canada profile keeps evaluation in Canadian regions.
    const guardrail = new bedrock.CfnGuardrail(this, 'Guardrail', {
      name: 'career-assistant',
      crossRegionConfig: { guardrailProfileArn: GUARDRAIL_PROFILE_ARN(this) },
      description: 'Career Assistant demo guardrail',
      blockedInputMessaging:
        'Je ne peux pas répondre à cette demande. / I cannot help with that request.',
      blockedOutputsMessaging:
        'Je ne peux pas répondre à cette demande. / I cannot help with that request.',
      sensitiveInformationPolicyConfig: {
        piiEntitiesConfig: [
          'EMAIL',
          'PHONE',
          'ADDRESS',
          'CA_SOCIAL_INSURANCE_NUMBER',
          'CA_HEALTH_NUMBER',
          'CREDIT_DEBIT_CARD_NUMBER',
        ].map((type) => ({
          type,
          action: 'ANONYMIZE',
          // explicit per-direction settings: left unset, nothing is detected
          inputAction: 'ANONYMIZE',
          outputAction: 'ANONYMIZE',
          inputEnabled: true,
          outputEnabled: true,
        })),
      },
      topicPolicyConfig: {
        topicsConfig: [
          {
            name: 'CandidateEvaluation',
            type: 'DENY',
            definition:
              'Requests to assess, score, rank or predict the hiring outcome of a specific person or candidate.',
            examples: [
              'Est-ce que mon profil a des chances d’être retenu ?',
              'Rate my resume out of 10 for this job',
            ],
          },
          {
            name: 'PersonalInsuranceFile',
            type: 'DENY',
            definition:
              'The user asks about their own personal insurance file: the status of their own claim, ' +
              'their policy, their quote or their premium. Questions about jobs, careers or roles ' +
              'in claims or insurance (such as claims adjuster positions) are not part of this topic.',
            examples: [
              'Où en est ma réclamation auto ?',
              'How much is my home insurance premium?',
              'Pouvez-vous modifier ma police d’assurance ?',
            ],
          },
          {
            name: 'Politics',
            type: 'DENY',
            definition: 'Political opinions, elections, political parties or politicians.',
            examples: ['Pour qui devrais-je voter ?'],
          },
        ].map((topic) => ({
          ...topic,
          inputEnabled: true,
          inputAction: 'BLOCK',
          outputEnabled: false, // answers are grounded in career pages; saves one evaluation per turn
        })),
        topicsTierConfig: { tierName: 'STANDARD' },
      },
      contentPolicyConfig: {
        filtersConfig: [{ type: 'PROMPT_ATTACK', inputStrength: 'HIGH', outputStrength: 'NONE' }],
        contentFiltersTierConfig: { tierName: 'STANDARD' },
      },
    })

    // ---------- Knowledge base: public career pages -> S3 Vectors ----------
    const docs = new s3.Bucket(this, 'KbDocs', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      autoDeleteObjects: true,
      ...demo,
    })
    const kbUpload = new s3deploy.BucketDeployment(this, 'KbDocsUpload', {
      destinationBucket: docs,
      sources: kbSources(),
      prune: true,
    })

    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', {})
    const vectorIndex = new s3vectors.CfnIndex(this, 'VectorIndex', {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: 'career-content',
      dataType: 'float32',
      dimension: EMBEDDING_DIMENSIONS,
      distanceMetric: 'cosine',
      // Bedrock stores chunk text + metadata here; keep them out of the 2 KB filterable budget
      metadataConfiguration: {
        nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'],
      },
    })

    const embeddingArn = `arn:aws:bedrock:${this.region}::foundation-model/${EMBEDDING_MODEL}`
    const kbRole = new iam.Role(this, 'KbRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': this.account } },
      }),
    })
    docs.grantRead(kbRole)
    kbRole.addToPolicy(
      new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: [embeddingArn] }),
    )
    kbRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          's3vectors:PutVectors',
          's3vectors:GetVectors',
          's3vectors:DeleteVectors',
          's3vectors:QueryVectors',
          's3vectors:GetIndex',
        ],
        resources: [vectorIndex.attrIndexArn],
      }),
    )

    const kb = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase', {
      name: 'career-assistant-kb',
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: embeddingArn,
          embeddingModelConfiguration: {
            bedrockEmbeddingModelConfiguration: { dimensions: EMBEDDING_DIMENSIONS },
          },
        },
      },
      storageConfiguration: {
        type: 'S3_VECTORS',
        s3VectorsConfiguration: {
          vectorBucketArn: vectorBucket.attrVectorBucketArn,
          indexArn: vectorIndex.attrIndexArn,
        },
      },
    })
    kb.node.addDependency(kbRole) // the role policy must exist before Bedrock validates it

    const dataSource = new bedrock.CfnDataSource(this, 'KbDataSource', {
      knowledgeBaseId: kb.attrKnowledgeBaseId,
      name: 'public-career-pages',
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: { bucketArn: docs.bucketArn },
      },
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: 'FIXED_SIZE',
          fixedSizeChunkingConfiguration: { maxTokens: 300, overlapPercentage: 15 },
        },
      },
    })

    // Re-index after every deploy that changes the documents
    const ingest = new cr.AwsCustomResource(this, 'KbIngestion', {
      onUpdate: {
        service: 'bedrock-agent',
        action: 'StartIngestionJob',
        parameters: {
          knowledgeBaseId: kb.attrKnowledgeBaseId,
          dataSourceId: dataSource.attrDataSourceId,
        },
        physicalResourceId: cr.PhysicalResourceId.of(`ingest-${kbContentHash()}`),
      },
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ['bedrock:StartIngestionJob'],
          resources: [kb.attrKnowledgeBaseArn],
        }),
      ]),
      installLatestAwsSdk: false,
    })
    ingest.node.addDependency(kbUpload)

    // ---------- API: FastAPI on Lambda (arm64) behind an HTTP API ----------
    const fn = new lambda.Function(this, 'Api', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'app.main.handler',
      code: backendCode(),
      memorySize: 512,
      timeout: cdk.Duration.seconds(29),
      logGroup: new logs.LogGroup(this, 'ApiLogs', {
        retention: logs.RetentionDays.ONE_WEEK,
        ...demo,
      }),
      environment: {
        CA_MODE: 'aws',
        CA_AWS_REGION: this.region,
        CA_MODEL_ID: modelId,
        CA_TABLE_NAME: table.tableName,
        CA_KNOWLEDGE_BASE_ID: kb.attrKnowledgeBaseId,
        CA_GUARDRAIL_ID: guardrail.attrGuardrailId,
        CA_GUARDRAIL_VERSION: 'DRAFT',
      },
    })
    table.grantReadWriteData(fn)
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel'],
        resources: Object.entries(MODELS).flatMap(([profile, model]) => [
          `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/${profile}`,
          `arn:aws:bedrock:*::foundation-model/${model}`, // profile may route to ca-west-1
        ]),
      }),
    )
    fn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ['bedrock:Retrieve'], resources: [kb.attrKnowledgeBaseArn] }),
    )
    // Read-only check Bedrock performs before serving a Marketplace model (Claude)
    fn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ['aws-marketplace:ViewSubscriptions'], resources: ['*'] }),
    )
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:ApplyGuardrail'],
        resources: [
          guardrail.attrGuardrailArn,
          // the Canada profile may evaluate in ca-central-1 or ca-west-1
          `arn:aws:bedrock:*:${this.account}:guardrail-profile/${GUARDRAIL_PROFILE}`,
        ],
      }),
    )

    const api = new apigw.HttpApi(this, 'HttpApi', {
      defaultIntegration: new HttpLambdaIntegration('ApiIntegration', fn),
      createDefaultStage: false,
    })
    new apigw.HttpStage(this, 'Stage', {
      httpApi: api,
      stageName: '$default',
      autoDeploy: true,
      throttle: { rateLimit: 5, burstLimit: 10 }, // demo traffic only: caps the bill
    })

    // ---------- Widget: S3 + CloudFront, /api/* routed to the HTTP API ----------
    const site = new s3.Bucket(this, 'Site', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      autoDeleteObjects: true,
      ...demo,
    })
    const cdn = new cloudfront.Distribution(this, 'Cdn', {
      defaultRootObject: 'index.html',
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100, // North America + Europe edges
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(site),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      },
      additionalBehaviors: {
        '/api/*': {
          origin: new origins.HttpOrigin(`${api.apiId}.execute-api.${this.region}.amazonaws.com`),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
    })
    new s3deploy.BucketDeployment(this, 'SiteUpload', {
      destinationBucket: site,
      sources: [s3deploy.Source.asset(frontendDist())],
      distribution: cdn,
      distributionPaths: ['/*'],
    })

    new cdk.CfnOutput(this, 'SiteUrl', { value: `https://${cdn.distributionDomainName}` })
    new cdk.CfnOutput(this, 'ApiUrl', { value: api.apiEndpoint })
    new cdk.CfnOutput(this, 'KnowledgeBaseId', { value: kb.attrKnowledgeBaseId })
    new cdk.CfnOutput(this, 'ModelId', { value: modelId })
  }
}

/** Python Lambda package built locally (no Docker): pip wheels for Linux arm64 + app code. */
function backendCode(): lambda.Code {
  const python =
    process.env.PYTHON ??
    (process.platform === 'win32' ? join(BACKEND, '.venv', 'Scripts', 'python.exe') : 'python3')
  return lambda.Code.fromAsset(BACKEND, {
    exclude: ['.venv', 'tests', '**/__pycache__', '.pytest_cache', '.ruff_cache', '.env*'],
    bundling: {
      image: lambda.Runtime.PYTHON_3_12.bundlingImage,
      command: [
        'bash',
        '-c',
        'pip install -r requirements-lambda.txt -t /asset-output && cp -r app data /asset-output',
      ],
      local: {
        tryBundle(outputDir: string) {
          execFileSync(
            python,
            [
              '-m', 'pip', 'install', '-q',
              '-r', join(BACKEND, 'requirements-lambda.txt'),
              '--target', outputDir,
              '--platform', 'manylinux2014_aarch64',
              '--implementation', 'cp',
              '--python-version', '3.12',
              '--only-binary=:all:',
            ],
            { stdio: 'inherit' },
          )
          cpSync(join(BACKEND, 'app'), join(outputDir, 'app'), {
            recursive: true,
            filter: (src) => !src.includes('__pycache__'),
          })
          mkdirSync(join(outputDir, 'data'), { recursive: true })
          cpSync(join(BACKEND, 'data', 'jobs.json'), join(outputDir, 'data', 'jobs.json'))
          return true
        },
      },
    },
  })
}

function frontendDist(): string {
  if (!existsSync(join(FRONTEND_DIST, 'index.html'))) {
    throw new Error('frontend/dist is missing: run `npm run build` in frontend/ first')
  }
  return FRONTEND_DIST
}

/** Markdown pages + Bedrock `<file>.metadata.json` sidecars (title, source_url). */
function kbSources(): s3deploy.ISource[] {
  const files = readdirSync(KB_DIR).filter((f) => f.endsWith('.md'))
  if (files.length === 0) throw new Error(`no .md files in ${KB_DIR}`)
  return files.flatMap((file) => {
    const raw = readFileSync(join(KB_DIR, file), 'utf-8')
    const field = (key: string) => raw.match(new RegExp(`^${key}:\\s*(.+)$`, 'm'))?.[1].trim()
    const metadataAttributes: Record<string, string> = { title: field('title') ?? file }
    const url = field('source_url')
    if (url) metadataAttributes.source_url = url
    return [
      s3deploy.Source.data(file, raw),
      s3deploy.Source.jsonData(`${file}.metadata.json`, { metadataAttributes }),
    ]
  })
}

function kbContentHash(): string {
  const h = createHash('sha256')
  for (const f of readdirSync(KB_DIR).sort()) h.update(f).update(readFileSync(join(KB_DIR, f)))
  return h.digest('hex').slice(0, 12)
}
