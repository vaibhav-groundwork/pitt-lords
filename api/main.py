"""
Pitt-Lords API -- FastAPI application.

Two known, accepted limitations of the BackgroundTasks-based pipeline, not to
be solved here:
  (1) If the server process restarts mid-task, the in-progress task is lost
      with no automatic resume. The leases row will remain stuck in its
      current in-progress stage indefinitely.
  (2) There is no timeout guard on the individual pipeline stages. If an
      underlying API call hangs (Anthropic or OpenAI), the lease will appear
      stuck in that stage with no automatic failure or alerting.

CORS configuration note: the middleware block below is locked to localhost for
now. Once the frontend is built and deployed, update allow_origins to include
the real frontend origin. Never use "*" once real lease data is flowing.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from agents import compliance_diff, document_extract, lease_parser, report_builder, verifier
from api.config import settings
from api.db import get_connection

# Temporary upload directory. The directory is created on first use by the
# upload handler. Files are deleted in the background task's finally block
# regardless of success or failure.
_UPLOAD_DIR = Path("/tmp/pitt-lords-uploads")

# Allowed upload extensions (lowercase). document_extract performs its own
# validation as a second defensive layer, but the API gives a fast, friendly
# rejection first.
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}


app = FastAPI(
    title="Pitt-Lords API",
    description="Lease compliance checklist assistant for Pittsburgh, PA landlords. "
                "Informational tool only -- not legal advice.",
    version="0.1.0",
)

# CORS locked down to known frontend origins. Update this list as you deploy --
# never use "*" once real lease data is flowing through this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://pitt-lords.vercel.app"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_lease_status(
    conn,
    lease_id: str,
    status: str,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Update the leases row for lease_id to a new status.

    Used exclusively by the background processing function for stage
    transitions and the terminal failure state. The initial INSERT that
    creates the row is a plain statement in POST /leases, not routed
    through this helper.

    Parameters
    ----------
    conn:
        An open psycopg connection with ``autocommit=True``.
    lease_id:
        UUID string identifying the lease being updated.
    status:
        New value for leases.status. Must match the CHECK constraint:
        'uploaded', 'extracting_text', 'parsing_clauses',
        'checking_compliance', 'verifying', 'complete', 'failed'.
    error_message:
        Written to leases.error_message. Pass None to leave it unchanged;
        the failure path passes the exception message here.
    completed_at:
        Written to leases.completed_at when the pipeline finishes (both
        'complete' and 'failed').
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE leases
            SET status = %(status)s,
                error_message = COALESCE(%(error_message)s, error_message),
                completed_at = COALESCE(%(completed_at)s, completed_at)
            WHERE id = %(lease_id)s
            """,
            {
                "status": status,
                "error_message": error_message,
                "completed_at": completed_at,
                "lease_id": lease_id,
            },
        )


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def process_lease_background(lease_id: str, file_path: str) -> None:
    """Run the full five-stage pipeline for an uploaded lease.

    Plain ``def`` (not ``async def``) so FastAPI/Starlette dispatches this to
    a thread-pool worker rather than the event loop -- all five pipeline stages
    are synchronous/blocking and must not run on the event loop.

    Stages, in order:
      1. document_extract.extract_text    -> leases.status = 'extracting_text'
      2. lease_parser.parse_lease         -> leases.status = 'parsing_clauses'
      3. compliance_diff.run_compliance_diff -> leases.status = 'checking_compliance'
      4. verifier.run_verifier            -> leases.status = 'verifying'
      5. (done)                           -> leases.status = 'complete'

    Any unhandled exception at any stage (including document_extract.ValueError
    for unreadable/scanned PDFs and verifier.RuntimeError for a missing
    OPENAI_API_KEY) is caught by the outer except block and written to
    leases.error_message. The exception's message is already descriptive in
    both of those cases; no special-casing is needed.

    The temp file at file_path is deleted in the finally block regardless of
    success or failure so uploaded files do not accumulate on disk.

    Parameters
    ----------
    lease_id:
        UUID string matching the row inserted by POST /leases.
    file_path:
        Absolute path to the temp file written by POST /leases. Deleted on
        exit regardless of outcome.
    """
    conn = get_connection()
    try:
        _update_lease_status(conn, lease_id, "extracting_text")
        text = document_extract.extract_text(file_path)

        _update_lease_status(conn, lease_id, "parsing_clauses")
        lease_parser.parse_lease(text, lease_id=lease_id)

        _update_lease_status(conn, lease_id, "checking_compliance")
        compliance_diff.run_compliance_diff(lease_id)

        _update_lease_status(conn, lease_id, "verifying")
        verifier.run_verifier(lease_id)

        _update_lease_status(
            conn,
            lease_id,
            "complete",
            completed_at=datetime.now(timezone.utc),
        )

    except Exception as exc:
        _update_lease_status(
            conn,
            lease_id,
            "failed",
            error_message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )

    finally:
        conn.close()
        try:
            os.remove(file_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Confirms the API is up AND can actually reach Postgres -- not just a ping."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()
    return {"status": "ok", "environment": settings.environment}


@app.post("/leases", status_code=202)
async def upload_lease(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Accept a lease PDF or DOCX for async compliance processing.

    Validates the file extension and size, writes the file to a temp path
    keyed only on a freshly-generated lease_id (never on the original
    filename), inserts a leases row, and schedules the five-stage pipeline
    as a background task.

    Parameters
    ----------
    file:
        Uploaded .pdf or .docx file. Maximum size is ``settings.max_upload_mb``.

    Returns
    -------
    dict
        ``{"lease_id": <uuid>, "status": "uploaded"}`` with HTTP 202.

    Raises
    ------
    HTTPException 400:
        If the file extension is not .pdf or .docx, or if the file exceeds
        the size limit.
    """
    # Validate extension before reading the file contents.
    original_name = file.filename or ""
    file_extension = Path(original_name).suffix.lower()
    if file_extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{file_extension}'. "
                "Only .pdf and .docx files are accepted."
            ),
        )

    # Read the file bytes exactly once. The stream is exhausted after this
    # call; `contents` must be reused for both the size check and the disk
    # write below.
    contents = await file.read()

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File exceeds the {settings.max_upload_mb} MB upload limit "
                f"({len(contents) / 1024 / 1024:.1f} MB uploaded)."
            ),
        )

    lease_id = str(uuid.uuid4())

    # Build the temp path from the lease_id only. The original filename is
    # stored as plain data in the leases row but must never influence where
    # a file is written on disk -- this is a security boundary, not just
    # collision-avoidance.
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = str(_UPLOAD_DIR / f"{lease_id}{file_extension}")

    with open(file_path, "wb") as f:
        f.write(contents)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leases (id, original_filename, status)
                VALUES (%s, %s, 'uploaded')
                """,
                (lease_id, original_name),
            )
    except Exception as exc:
        # The temp file was already written; clean it up before surfacing the
        # error so it doesn't linger on disk with no lease_id to reference it.
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record lease in database: {exc}",
        ) from exc
    finally:
        conn.close()

    background_tasks.add_task(process_lease_background, lease_id, file_path)

    return {"lease_id": lease_id, "status": "uploaded"}


@app.get("/leases/{lease_id}")
def get_lease_status(lease_id: str) -> dict[str, Any]:
    """Poll the processing status of a previously uploaded lease.

    Returns HTTP 200 for all three meaningful states (in-progress, complete,
    failed) -- the request itself succeeded in all cases; the JSON body
    communicates what happened with the pipeline. A failed pipeline run is not
    an API-level error. The one true 404 case is when the lease_id does not
    exist in the leases table at all.

    Parameters
    ----------
    lease_id:
        UUID string returned by POST /leases.

    Returns
    -------
    dict
        In-progress: ``{"lease_id", "status"}``.
        Failed: ``{"lease_id", "status": "failed", "error_message"}``.
        Complete: ``{"lease_id", "status": "complete", "report": {...}}``.
        The report is generated fresh on every call rather than stored.

    Raises
    ------
    HTTPException 404:
        If no leases row exists for this lease_id.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, error_message
                FROM leases
                WHERE id = %s
                """,
                (lease_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No lease found with id '{lease_id}'.",
        )

    status, error_message = row

    if status == "failed":
        return {
            "lease_id": lease_id,
            "status": "failed",
            "error_message": error_message,
        }

    if status == "complete":
        report = report_builder.generate_report(lease_id)
        return {
            "lease_id": lease_id,
            "status": "complete",
            "report": report,
        }

    # Any in-progress stage ('uploaded', 'extracting_text', 'parsing_clauses',
    # 'checking_compliance', 'verifying') -- tell the caller to keep polling.
    return {"lease_id": lease_id, "status": status}
