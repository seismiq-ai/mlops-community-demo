import boto3
import requests
import json
import psycopg2
from datetime import datetime, timedelta
import os
import logging
import uuid
import html
import re
from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    try:
        # Connect to Postgres
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        cur = conn.cursor()

        # Get new filings from the database
        cur.execute(
            """
            SELECT cik, accession_number, form, archive_url
            FROM company_filings
            WHERE processed = FALSE OR sentiment IS NULL
        """
        )
        new_filings = cur.fetchall()

        conn.commit()
        cur.close()
        conn.close()

        s3 = boto3.client("s3")
        bucket_name = os.environ["S3_BUCKET"]

        sqs = boto3.client("sqs")
        queue_url = os.environ["SQS_URL"]
        batch_id = str(uuid.uuid4())

        file_names = []
        failed_files = []
        for filing in new_filings:
            cik, accession_number, form, archive_url = filing

            try:
                # Fetch the filing document
                headers = {"User-Agent": "Seismiq info@seismiq.ai"}
                response = requests.get(archive_url, headers=headers)
                response.raise_for_status()
                content = response.content

                # Clean the htm document
                clean_content = html.unescape(content.decode('utf-8'))
                text_content = re.sub('<[^<]+?>', '', clean_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                print(f"cleaned: {text_content}")

                # Store the document in S3 with its original extension
                file_extension = ".txt"
                file_name = f"filings/{cik}/{form}_{accession_number}{file_extension}"
                s3.put_object(Bucket=bucket_name, Key=file_name, Body=text_content.encode('utf-8'))

                message_body = json.dumps(
                    {
                        "bucket": bucket_name,
                        "key": file_name,
                        "cik": cik,
                        "accession_number": accession_number,
                        "form": form,
                    }
                )
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=message_body,
                    MessageAttributes={
                        "batch_id": {"DataType": "String", "StringValue": batch_id}
                    },
                )

                file_names.append(file_name)
            except Exception as e:
                logger.error(
                    f"Error processing filing {cik}/{accession_number}: {str(e)}"
                )
                failed_files.append(file_name)

        return {
            "batch_id": batch_id,
            "file_names": file_names,
            "failed_files": failed_files,
            "file_count": len(file_names)
        }
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        raise Exception(f"InternalServerError: {str(e)}")
