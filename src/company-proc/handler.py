import boto3
import json
import psycopg2
from psycopg2.extras import Json
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_company_facts(company_data):
    return {
        "cik": company_data.get("cik"),
        "sic": company_data.get("sic"),
        "sic_description": company_data.get("sicDescription"),
        "owner_org": company_data.get("ownerOrg"),
        "name": company_data.get("name"),
        "tickers": company_data.get("tickers") or [],
        "exchanges": company_data.get("exchanges") or [],
        "ein": company_data.get("ein"),
        "description": company_data.get("description"),
        "website": company_data.get("website"),
        "category": company_data.get("category"),
        "state_of_incorporation": company_data.get("stateOfIncorporation"),
    }


def save_company_facts(cur, company_facts):
    cur.execute(
        """
        INSERT INTO company_facts (
            cik, sic, sic_description, owner_org, entity_name, tickers, exchanges,
            ein, description, website, category, state_of_incorporation, last_updated
        )
        VALUES (%(cik)s, %(sic)s, %(sic_description)s, %(owner_org)s, %(name)s, 
                ARRAY[%(tickers)s], ARRAY[%(exchanges)s], %(ein)s, %(description)s, %(website)s, 
                %(category)s, %(state_of_incorporation)s, %(last_updated)s)
        ON CONFLICT (cik) DO UPDATE
        SET sic = EXCLUDED.sic,
            sic_description = EXCLUDED.sic_description,
            owner_org = EXCLUDED.owner_org,
            entity_name = EXCLUDED.entity_name,
            tickers = EXCLUDED.tickers,
            exchanges = EXCLUDED.exchanges,
            ein = EXCLUDED.ein,
            description = EXCLUDED.description,
            website = EXCLUDED.website,
            category = EXCLUDED.category,
            state_of_incorporation = EXCLUDED.state_of_incorporation,
            last_updated = EXCLUDED.last_updated
        """,
        {**company_facts, "last_updated": datetime.now()},
    )


def save_recent_filings(cur, cik, recent_filings):
    for filing in recent_filings:
        accession_number_dashless = filing["accession_number"].replace("-", "")
        primary_doc = filing["primary_doc"]
        archive_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number_dashless}/{primary_doc}"
        cur.execute(
            """
            INSERT INTO company_filings (
                cik, form, filing_date, accession_number, primary_doc, archive_url
            )
            VALUES (%(cik)s, %(form)s, %(filing_date)s, %(accession_number)s, %(primary_doc)s, %(archive_url)s)
            ON CONFLICT (cik, accession_number) DO UPDATE
            SET archive_url = EXCLUDED.archive_url
            """,
            {**filing, "cik": cik, "archive_url": archive_url},
        )


def get_recent_filings(company_data):
    recent_filings = company_data.get("filings", {}).get("recent", {})
    forms = recent_filings.get("form", [])
    filing_dates = recent_filings.get("filingDate", [])
    accession_numbers = recent_filings.get("accessionNumber", [])
    primary_doc = recent_filings.get("primaryDocument", [])

    filings = []
    for form, filing_date, accession_number, primary_doc in zip(
        forms, filing_dates, accession_numbers, primary_doc
    ):
        if form in ["10-K", "8-K", "10-Q"]:
            filings.append(
                {
                    "form": form,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "primary_doc": primary_doc,
                }
            )
            if len(filings) == 2:
                break

    return filings


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    bucket_name = os.environ["S3_BUCKET"]

    try:
        # Get the list of CIKs from the event
        cik_list = event.get("cik_list", [])

        if not cik_list:
            raise ValueError("No CIK values provided")

        # Connect to Postgres
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        cur = conn.cursor()

        results = []
        for cik in cik_list:
            try:
                cik_padded = cik.zfill(10)
                key = f"submissions/CIK{cik_padded}.json"

                response = s3.get_object(Bucket=bucket_name, Key=key)
                company_data = json.loads(response["Body"].read().decode("utf-8"))

                company_facts = get_company_facts(company_data)
                recent_filings = get_recent_filings(company_data)
                save_company_facts(cur, company_facts)
                save_recent_filings(cur, cik, recent_filings)
                results.append({"cik": cik, "status": "success"})
            except Exception as e:
                logger.error(f"Error processing CIK {cik}: {str(e)}")
                results.append({"cik": cik, "status": "error", "message": str(e)})
                conn.rollback()

        conn.commit()
        cur.close()
        conn.close()

        return {"CompanyProc": "OK"}
    except psycopg2.Error as e:
        logger.error(f"Database error: {str(e)}")
        raise Exception(f"DatabaseConnectionError: {str(e)}")
    except ValueError as e:
        raise Exception(f"BadRequest: {str(e)}")
    except Exception as e:
        raise Exception(f"InternalServerError: {str(e)}")
