# Data pipelines in production

A workshop about taking pipelines from development to prod:

* Initial work using AWS Lambda, S3, and EventBridge with Postgres (Neon)
* Checklist for production: testing, deployment, data management policies, security, and monitoring
* When + how to scale up: compute, storage, orchestration, and/or database


## Prereqs

We'll be using a Python project (poetry) with the [US SEC's EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). No API is required, merely a user-agent header.

For local deveopment, we'll be using Docker and pytest.

For deployment, we'll be using Pulumi (Python) to ship to AWS.


## Pipeline: Daily SEC filings ingest

1. `company-ingest`:` Triggered daily at 2am. Fetch the latest available company submissions (JSON) for a short list of public tech companies: Meta, Apple, Amazon, Microsoft. Save them to S3.

1. `company-proc`: Next in Step Functions. Take JSON from S3 and update the company_facts and company_filings tables in Postgres. Company filings include Q-10 and K-8.

1. `filings-ingest`: Nex in Step Functions. Get new filings docnames from Postgres. Fetch the new filings via the SEC EDGAR API as JSON and store them to S3 as csv's. 

1. `embeddings`: Next in Step Functions, in parallel with Sentiment analysis. Generate embeddings for each new document using OpenAI's API and store results to Postgres (pg_vector extension). Use concurrent API requests to minimize Lambda lifetime.

1. `sentiment`: AWS Lambda invoked by an SQS queue. Computes sentiment scores from document text and stores results in the company_filings table Postgres. 

1. `filings-queue`: Next in Step Functions, in parallel with Embeddings generation. Monitors the SQS queue progress of "sentiment" Lambdas computing sentiment scores. Uses a callback pattern: monitors an SQS queue for progress and returns results when done.

1. `final-report`: Final in Step Functions. Saves report and any errors to S3 as a new JSON file.

1. `error-handler`: Handles exceptions thrown during the Step Functions workflow


## Local dev

Checking a Step Functions-invoked Lambda is a little different than an HTTP-invoked one. Use the following runner.py:

```
import json
from handler import lambda_handler


def simulate_step_function_invoke(ciks):
    return {"cik_list": ciks}


def main():
    # Sample CIK list - replace with your desired CIKs
    cik_list = ["320193", "789019", "1018724", "1326801", "1652044"]

    # Simulate Lambda event
    event = simulate_step_function_invoke(cik_list)

    # Call the lambda_handler function
    result = lambda_handler(event, None)

    # Print the result
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

## Deployment

1. Update the requirements.txt: 

```
 poetry export -f requirements.txt --output requirements.base.txt --without deploy --without-hashes
 ```


 1. Run the Lambda Layer builder script:

 ```
 ./build_layer.sh
 ```


 1. Make sure you have environment variables set in your .env:

 ```
S3_BUCKET=
SQS_URL=
DLQ_URL=
OPENAI_API_KEY=

DB_HOST=
DB_NAME=
DB_USER=
DB_PASSWORD=
```

1. Make sure you have cloud (here, AWS) credentials set up

1. Deploy!

```
poetry install --all-extras
poetry run pulumi up
```

1. Tear down! `poetry run pulumi down`