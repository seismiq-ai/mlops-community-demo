import boto3
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()


def lambda_handler(event, context):
    try:
        cik_list = event.get("cik_list", [])

        if not cik_list:
            raise ValueError("No CIK values provided")

        results = []
        for cik in cik_list:
            cik_padded = cik.zfill(10)

            try:
                url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
                headers = {"User-Agent": "Seismiq info@seismiq.ai"}
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                company_submissions = response.json()

                s3_client = boto3.client("s3")
                bucket_name = os.environ["S3_BUCKET"]
                file_name = f"submissions/CIK{cik_padded}.json"

                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_name,
                    Body=json.dumps(company_submissions),
                    ContentType="application/json",
                )

                results.append({"cik": cik, "status": "success"})
            except requests.RequestException as e:
                results.append({"cik": cik, "status": "error", "message": str(e)})
            except Exception as e:
                results.append({"cik": cik, "status": "error", "message": str(e)})

        return {"CompanyIngest": "OK"}
    except ValueError as e:
        raise Exception(f"BadRequest: {str(e)}")
    except Exception as e:
        raise Exception(f"InternalServerError: {str(e)}")
