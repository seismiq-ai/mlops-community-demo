import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx
import os
import sys
import json
from dotenv import load_dotenv
from typing import Dict, List
import logging
import hashlib


logging.basicConfig(level=logging.INFO)

load_dotenv()

# Constants
RUNTIME = "python3.12"
BUCKET_NAME = "sec-filings-2341180373"
CIK_LIST = [
    "320193",  # Apple Inc
    "789019",  # Microsoft
    "1018724",  # Amazon
    "1326801",  # Meta
    "1652044",  # Alphabet
]

COMMON_ENV_VARS = {
    "S3_BUCKET": os.environ["S3_BUCKET"],
    "SQS_URL": os.environ["SQS_URL"],
    "DLQ_URL": os.environ["DLQ_URL"],
    "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
    "DB_HOST": os.environ["DB_HOST"],
    "DB_NAME": os.environ["DB_NAME"],
    "DB_USER": os.environ["DB_USER"],
    "DB_PASSWORD": os.environ["DB_PASSWORD"],
}

# Create S3 bucket
sec_filings_bucket = aws.s3.Bucket(
    BUCKET_NAME,
    bucket=BUCKET_NAME,
    acl="private",
    force_destroy=True,
)

# Upload Lambda Layer to S3
base_layer_object = aws.s3.BucketObject(
    "base-layer-object",
    bucket=sec_filings_bucket.id,
    key="layers/base_layer.zip",
    source=pulumi.FileAsset("./layers/base/base_layer.zip"),
)

# Create Lambda Layer
base_layer = aws.lambda_.LayerVersion(
    "base-layer",
    layer_name="base-layer",
    s3_bucket=sec_filings_bucket.id,
    s3_key=base_layer_object.key,
    compatible_runtimes=[RUNTIME],
)

# Create IAM role for Lambda functions
lambda_role = aws.iam.Role(
    "lambdaRole",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": ["lambda.amazonaws.com", "states.amazonaws.com"]
                    },
                }
            ],
        }
    ),
)

# Attach basic execution role policy
aws.iam.RolePolicyAttachment(
    "lambdaRolePolicy",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
)

# Attach additional policy for Step Functions execution
aws.iam.RolePolicyAttachment(
    "stepFunctionsExecutionPolicy",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaRole",
)

# Allow Lambda functions to access S3 and specific Step Functions
s3_access_policy = aws.iam.Policy(
    "s3AccessPolicy",
    policy=pulumi.Output.all(bucket_arn=sec_filings_bucket.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:ListBucket",
                            "s3:DeleteObject",
                        ],
                        "Resource": [
                            args["bucket_arn"],
                            f"{args['bucket_arn']}/*",
                        ],
                    },
                ],
            }
        )
    ),
)

aws.iam.RolePolicyAttachment(
    "s3AccessPolicyAttachment",
    role=lambda_role.name,
    policy_arn=s3_access_policy.arn,
)

# Create SQS queues
dlq_queue = aws.sqs.Queue(
    "deadletter-queue",
    name="sec-filings-deadletter-queue",
    message_retention_seconds=1209600,  # 14 days
)

sqs_queue = aws.sqs.Queue(
    "sentiment-queue",
    name="sec-filings-sentiment-queue",
    visibility_timeout_seconds=300,
    receive_wait_time_seconds=20,
    redrive_policy=dlq_queue.arn.apply(lambda arn: json.dumps({
        "deadLetterTargetArn": arn,
        "maxReceiveCount": 3
    }))
)

# Add SQS permissions to the Lambda role
sqs_access_policy = aws.iam.Policy(
    "sqsAccessPolicy",
    policy=pulumi.Output.all(queue_arn=sqs_queue.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "sqs:SendMessage",
                            "sqs:ReceiveMessage",
                            "sqs:DeleteMessage",
                            "sqs:GetQueueAttributes",
                        ],
                        "Resource": args["queue_arn"],
                    },
                ],
            }
        )
    ),
)

aws.iam.RolePolicyAttachment(
    "sqsAccessPolicyAttachment",
    role=lambda_role.name,
    policy_arn=sqs_access_policy.arn,
)




# Get Lambda function names from subdirectories
LAMBDA_FUNCTIONS = [
    name for name in os.listdir("./src") if os.path.isdir(os.path.join("./src", name))
]
print(f"Lambdas found: {str(LAMBDA_FUNCTIONS)}")

lambda_functions = {}
for function_name in LAMBDA_FUNCTIONS:
    # Create the Lambda function
    memory_size = 256 if function_name == "embeddings" else 128
    lambda_function = aws.lambda_.Function(
        f"{function_name}-lambda",
        name=function_name,
        runtime=RUNTIME,
        handler="handler.lambda_handler",
        role=lambda_role.arn,
        code=pulumi.AssetArchive(
            {
                ".": pulumi.FileArchive(f"./src/{function_name}"),
            }
        ),
        layers=[base_layer.arn],
        environment={"variables": COMMON_ENV_VARS},
        timeout=300,
        memory_size=memory_size,
    )

    # If it's the sentiment Lambda, add SQS trigger
    if function_name == "sentiment":
        aws.lambda_.EventSourceMapping(
            "sentiment-sqs-trigger",
            event_source_arn=sqs_queue.arn,
            function_name=lambda_function.arn,
            batch_size=1,
            maximum_batching_window_in_seconds=0,
            scaling_config={
                "maximum_concurrency": 5,
            },
        )

    lambda_functions[function_name] = lambda_function
    pulumi.export(f"{function_name}_lambda_arn", lambda_function.arn)


# Define the entire state machine
state_machine_definition = pulumi.Output.all(
    **{k: v.arn for k, v in lambda_functions.items()}
).apply(
    lambda arns: json.dumps(
        {
            "Comment": "SEC Filings Workflow",
            "StartAt": "CompanyIngest",
            "States": {
                "CompanyIngest": {
                    "Type": "Task",
                    "Resource": arns["company-ingest"],
                    "Next": "CompanyProc",
                    "Parameters": {
                        "cik_list": CIK_LIST,
                    },
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 30,
                            "MaxAttempts": 2,
                            "BackoffRate": 2.0,
                        }
                    ],
                    "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ErrorHandler"}],
                },
                "CompanyProc": {
                    "Type": "Task",
                    "Resource": arns["company-proc"],
                    "Next": "FilingsIngest",
                    "Parameters": {
                        "cik_list": CIK_LIST,
                    },
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 30,
                            "MaxAttempts": 2,
                            "BackoffRate": 2.0,
                        }
                    ],
                    "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ErrorHandler"}],
                },
                "FilingsIngest": {
                    "Type": "Task",
                    "Resource": arns["filings-ingest"],
                    "Next": "ParallelProcessing",
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 30,
                            "MaxAttempts": 2,
                            "BackoffRate": 2.0,
                        }
                    ],
                    "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ErrorHandler"}],
                },
                "ParallelProcessing": {
                    "Type": "Parallel",
                    "Branches": [
                        {
                            "StartAt": "Embeddings",
                            "States": {
                                "Embeddings": {
                                    "Type": "Task",
                                    "Resource": arns["embeddings"],
                                    "Parameters": {"file_names.$": "$.file_names"},
                                    "End": True,
                                    "Retry": [
                                        {
                                            "ErrorEquals": ["States.TaskFailed"],
                                            "IntervalSeconds": 30,
                                            "MaxAttempts": 2,
                                            "BackoffRate": 2.0,
                                        }
                                    ],
                                }
                            },
                        },
                        {
                            "StartAt": "FilingsQueue",
                            "States": {
                                "FilingsQueue": {
                                    "Type": "Task",
                                    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
                                    "Parameters": {
                                        "FunctionName": arns["filings-queue"],
                                        "Payload": {
                                            "batch_id.$": "$.batch_id",
                                            "task_token.$": "$$.Task.Token",
                                        },
                                    },
                                    "End": True,
                                    "Retry": [
                                        {
                                            "ErrorEquals": ["States.TaskFailed"],
                                            "IntervalSeconds": 30,
                                            "MaxAttempts": 2,
                                            "BackoffRate": 2.0,
                                        }
                                    ],
                                }
                            },
                        },
                    ],
                    "Next": "FinalReport",
                    "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ErrorHandler"}],
                },
                "FinalReport": {
                    "Type": "Task",
                    "Resource": arns["final-report"],
                    "End": True,
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 30,
                            "MaxAttempts": 2,
                            "BackoffRate": 2.0,
                        }
                    ],
                    "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ErrorHandler"}],
                },
                "ErrorHandler": {
                    "Type": "Task",
                    "Resource": arns["error-handler"],
                    "End": True,
                },
            },
        }
    )
)

state_machine = aws.sfn.StateMachine(
    "sec-filings-workflow",
    role_arn=lambda_role.arn,
    definition=state_machine_definition,
)

# Add Step Functions permissions
sfn_access_policy = aws.iam.Policy(
    "sfnAccessPolicy",
    policy=pulumi.Output.all(state_machine_arn=state_machine.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "states:StartExecution",
                            "states:DescribeExecution",
                            "states:StopExecution",
                            "states:SendTaskSuccess",
                            "states:SendTaskFailure",
                        ],
                        "Resource": args["state_machine_arn"],
                    },
                ],
            }
        )
    ),
)

aws.iam.RolePolicyAttachment(
    "sfnAccessPolicyAttachment",
    role=lambda_role.name,
    policy_arn=sfn_access_policy.arn,
)


pulumi.export("bucket_name", sec_filings_bucket.id)
pulumi.export("sqs_queue_url", sqs_queue.url)
pulumi.export("dlq_queue_url", dlq_queue.url)
pulumi.export("state_machine_arn", state_machine.arn)
