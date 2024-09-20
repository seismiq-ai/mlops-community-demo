import json
import random
import os
import psycopg2
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def save_sentiment_to_db(message, sentiment_response):
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        cur = conn.cursor()

        cik = message["cik"]
        accession_number = message["accession_number"]

        # Update company_filings
        cur.execute(
            """
            UPDATE company_filings
            SET sentiment = %s
            WHERE cik = %s AND accession_number = %s
            RETURNING id
            """,
            (sentiment_response["Sentiment"], cik, accession_number),
        )

        conn.commit()
        cur.close()
        conn.close()

    except psycopg2.Error as e:
        raise Exception(f"DatabaseConnectionError: {str(e)}")


def lambda_handler(event, context):
    try:
        if 'Records' not in event or not event['Records']:
            logger.info("No messages in the event")
            return {
                "statusCode": 204,
                "body": json.dumps({"message": "No messages in event"}),
            }

        for record in event['Records']:
            message = record['body']
            logger.info(f"Received message: {message}")
            message_body = json.loads(message)
            
            # Mock sentiment analysis (keep your existing mock logic)
            sentiments = ["POSITIVE", "NEUTRAL", "NEGATIVE"]
            mock_sentiment = random.choice(sentiments)

            sentiment_response = {
                "Sentiment": mock_sentiment,
                "SentimentScore": {
                    "Positive": round(random.uniform(0, 1), 4),
                    "Neutral": round(random.uniform(0, 1), 4),
                    "Negative": round(random.uniform(0, 1), 4),
                    "Mixed": round(random.uniform(0, 0.1), 4),
                },
            }
            logger.info(f"Generated mock sentiment: {json.dumps(sentiment_response)}")

            save_sentiment_to_db(message_body, sentiment_response)
            logger.info("Successfully saved sentiment to database")

        return {"statusCode": 200, "body": json.dumps({"message": "Processed successfully"})}

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        raise Exception(f"InternalServerError: {str(e)}")