import json
import boto3
from datetime import datetime, UTC


def lambda_handler(event, context):
    """
    Error handler function for the Step Functions workflow.
    """
    execution_arn = event["Execution"]["Id"]
    state_name = event["Execution"]["Name"]
    error = event.get("Error", "Unknown error")
    cause = event.get("Cause", "Unknown cause")

    error_report = {
        "execution_arn": execution_arn,
        "state_name": state_name,
        "error": error,
        "cause": cause,
        "timestamp": datetime.utcnow().isoformat(),
    }

    s3_client = boto3.client("s3")
    bucket_name = "sec-filings"
    current_time = datetime.now(UTC)
    file_name = f"{current_time.strftime('%Y%m%d-%H%M%S')}-errors.json"
    s3_key = f"pipeline-reports/{file_name}"

    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(error_report, indent=2),
            ContentType="application/json",
        )
        print(f"Error report saved to s3://{bucket_name}/{s3_key}")
    except Exception as e:
        print(f"Failed to save error report to S3: {str(e)}")

    # You can add more error handling logic here, such as:
    # - Sending notifications
    # - Triggering a recovery process
    # - Updating the status of the workflow in a tracking system
