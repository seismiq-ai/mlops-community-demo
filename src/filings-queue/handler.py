import json
import boto3
import time
import os


def lambda_handler(event, context):
    sqs = boto3.client("sqs")
    sfn = boto3.client("stepfunctions")
    queue_url = os.environ["SQS_URL"]

    task_token = event["task_token"]
    batch_id = event["batch_id"]
    max_attempts = 5 
    sleep_time = 10 

    try:
        for attempt in range(max_attempts):
            # Check for messages with the given batch_id
            response = sqs.receive_message(
                QueueUrl=queue_url,
                AttributeNames=["All"],
                MessageAttributeNames=["batch_id"],
                MaxNumberOfMessages=10,
                VisibilityTimeout=0,
                WaitTimeSeconds=0,
            )

            matching_messages = [
                msg
                for msg in response.get("Messages", [])
                if msg.get("MessageAttributes", {})
                .get("batch_id", {})
                .get("StringValue")
                == batch_id
            ]

            if not matching_messages:
                # No more messages with this batch_id, we're done
                sfn.send_task_success(
                    taskToken=task_token,
                    output=json.dumps(
                        {
                            "status": "success",
                            "message": f"All messages for batch_id {batch_id} processed",
                        }
                    ),
                )
                return
            
            # Wait before checking again
            time.sleep(sleep_time)

        # If we've reached this point, we've exceeded max attempts
        sfn.send_task_failure(
            taskToken=task_token,
            error="ExecutionTimeout",
            cause=f"Timeout waiting for messages with batch_id {batch_id} to be processed",
        )

    except Exception as e:
        sfn.send_task_failure(
            taskToken=task_token, error="ExecutionError", cause=str(e)
        )
