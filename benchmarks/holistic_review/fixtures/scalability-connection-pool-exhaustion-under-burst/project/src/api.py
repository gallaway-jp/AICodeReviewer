from concurrent.futures import ThreadPoolExecutor

from db_pool import borrow_connection, release_connection


EXPORT_EXECUTOR = ThreadPoolExecutor(max_workers=64)


def persist_snapshot(connection, snapshot) -> None:
    return None


def process_export_job(job, fetch_remote_snapshot) -> None:
    connection = borrow_connection()
    try:
        snapshot = fetch_remote_snapshot(job["account_id"])
        persist_snapshot(connection, snapshot)
    finally:
        release_connection(connection)


def queue_export_jobs(jobs, fetch_remote_snapshot) -> list:
    futures = []
    for job in jobs:
        futures.append(EXPORT_EXECUTOR.submit(process_export_job, job, fetch_remote_snapshot))
    return futures