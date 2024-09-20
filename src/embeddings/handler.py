import json
import boto3
import os
import psycopg2
import openai
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_embedding(text):
    openai.api_key = os.environ["OPENAI_API_KEY"]
    response = openai.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding

def chunk_text(text, chunk_size=7200):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def process_file(bucket, key):
    try:
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")

        chunks = chunk_text(content)

        embeddings = []
        for chunk in chunks:
            embedding = get_embedding(chunk)
            embeddings.append(embedding)

        # Extract cik, form, and accession_number from the key
        parts = key.split("/")
        cik = parts[1]
        form, accession_number = parts[2].split("_")
        accession_number = accession_number.split(".")[0]  # Remove file extension

        return {
            "cik": cik,
            "accession_number": accession_number,
            "form": form,
            "embeddings": embeddings,
        }
    except Exception as e:
        logger.error(f"Error processing file {key}: {str(e)}")
        return None


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

        bucket = os.environ["S3_BUCKET"]
        file_names = event.get("file_names", [])
        logger.info(f"Processing {len(file_names)} files")

        # Process files concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_file, bucket, key) for key in file_names]
            results = []
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                    logger.info(
                        f"Successfully processed file: {result['cik']}/{result['form']}_{result['accession_number']}"
                    )
                else:
                    logger.warning("A file failed to process")

        logger.info(
            f"Successfully processed {len(results)} out of {len(file_names)} files"
        )

        # Store embeddings in Postgres
        embedding_batch = []
        for result in results:
            # Update company_filings
            cur.execute(
                """
                UPDATE company_filings
                SET processed = TRUE
                WHERE cik = %s AND accession_number = %s
                RETURNING id
                """,
                (result["cik"], result["accession_number"]),
            )
            filing_id = cur.fetchone()[0]

            for chunk_index, chunk_embedding in enumerate(result["embeddings"]):
                embedding_batch.append((
                    filing_id,
                    chunk_index,
                    json.dumps(chunk_embedding)
                ))
            
            cur.executemany(
                """
                INSERT INTO filing_embeddings (filing_id, chunk_index, embedding)
                VALUES (%s, %s, %s)
                ON CONFLICT (filing_id, chunk_index) DO UPDATE
                SET embedding = EXCLUDED.embedding
                """,
                embedding_batch
)
        conn.commit()
        cur.close()
        conn.close()

        logger.info("All database operations committed successfully")

        return { "files_processed": len(results) }
    except psycopg2.Error as e:
        logger.error(f"Database error: {str(e)}")
        raise Exception(f"DatabaseConnectionError: {str(e)}")
    except ValueError as e:
        raise Exception(f"BadRequest: {str(e)}")
    except Exception as e:
        raise Exception(f"InternalServerError: {str(e)}")
