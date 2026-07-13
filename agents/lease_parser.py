"""
Lease Parser Agent -- retrieval-augmented clause matching, not compliance judgment.

This agent answers one narrow question per legal requirement: does the lease
address this topic at all, and if so, what does it say verbatim? It does NOT
decide whether what the lease says is compliant with the law. That separation
matters because clause matching and compliance judgment are different reasoning
tasks that benefit from different prompts, different context windows, and
independent improvement cycles.

Retrieval-augmented design
--------------------------
The previous approach sent the full lease text plus a plain topic list to
Claude once per jurisdiction. This had two problems: it forced the model to
read the entire lease for every requirement even when most of the lease was
irrelevant to that topic, and it made no use of the pgvector embeddings already
computed during ingestion.

The new design:

  1. Chunk the lease into paragraph-sized pieces.
  2. Embed every chunk using the same all-MiniLM-L6-v2 model used during
     ingestion (embedding comparisons across different models are meaningless).
  3. For each chunk, retrieve the top-k most semantically similar requirements
     from legal_sources using pgvector cosine distance.
  4. Invert the retrieval results: build a map from requirement_key to the list
     of lease chunks that named it as a top-k candidate.
  5. Requirements that retrieved zero candidates anywhere in the lease are
     marked absent directly -- no LLM call needed. If the topic never appeared
     anywhere in embedding space, it almost certainly isn't in the lease.
  6. Requirements that do have candidates are batched and sent to Claude with
     their specific candidate excerpts, not the full lease text. The prompt
     explicitly warns Claude that retrieved candidates may not be relevant and
     instructs it to confirm genuine relevance rather than assuming a match.

This is materially different from the old approach: retrieval narrows each
requirement down to a small set of plausibly relevant lease excerpts before
asking the LLM to judge, rather than showing the LLM the entire lease text
repeatedly. It uses the pgvector embeddings that ingestion computed, it reduces
the tokens sent per LLM call, and it avoids LLM calls entirely for requirements
with no plausible match in the document.

Bidirectional retrieval -- attempted and reverted
--------------------------------------------------
A requirement -> chunk retrieval direction was added, then reverted, after
three rounds of eval-driven fixes each traded one failure mode for another
without net improvement over this baseline (which scores ~80% correct, zero
dangerous findings). Full history is logged in docs/decisions.md. Summary:
unconditional direction-2 retrieval eliminated the zero-candidates fast path
and diluted already-correct results; scoping it to zero-candidate requirements
only fixed that, but revealed that direction 1 alone can still assign a
requirement a technically-non-empty but wrong candidate in very short
documents, competing for scarce chunk slots against 73 other requirements --
a precision problem bidirectional retrieval cannot fix by construction. This
is logged as a known limitation and a candidate for a fresh architectural
look later, not patched further under time pressure.

Tool use is forced (tool_choice="tool") so responses are always structured JSON.
"""

import re
import sys
import uuid
from typing import Any

import anthropic
from sentence_transformers import SentenceTransformer

from api.config import settings
from api.db import get_connection

MODEL = SentenceTransformer("all-MiniLM-L6-v2")

_BATCH_SIZE = 25


Requirement = dict[str, Any]
Classification = dict[str, Any]


_RECORD_COMPLIANCE_CLASSIFICATIONS_TOOL: dict[str, Any] = {
    "name": "record_compliance_classifications",
    "description": (
        "Record whether each legal requirement topic is addressed in the lease "
        "and, if so, what the matching lease text says verbatim. "
        "Do NOT assess legal compliance -- only report presence and matched text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "description": "One entry per requirement_key supplied in the prompt.",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_key": {
                            "type": "string",
                            "description": "Exactly as supplied in the prompt.",
                        },
                        "addressed": {
                            "type": "boolean",
                            "description": (
                                "True if one of the provided candidate excerpts "
                                "genuinely addresses this topic."
                            ),
                        },
                        "matched_clause_text": {
                            "type": ["string", "null"],
                            "description": (
                                "Verbatim excerpt from the lease that addresses the topic, "
                                "or null if addressed is false."
                            ),
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score between 0.0 and 1.0.",
                        },
                    },
                    "required": [
                        "requirement_key",
                        "addressed",
                        "matched_clause_text",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["classifications"],
    },
}


def chunk_lease_text(lease_text: str) -> list[str]:
    """Split a lease document into paragraph-sized chunks for embedding."""
    _MIN_CHUNKS = 10
    _LARGE_TEXT = 5_000
    _OVERSIZED_CHUNK = 800
    _MIN_CHUNK_CHARS = 20
    _PAGE_BREAK = "[PAGE_BREAK]"
    _SENTENCE_END = re.compile(r"[.?!:]\s*$")

    def _resolve_page_breaks(text: str) -> str:
        parts = text.split(_PAGE_BREAK)
        result: list[str] = []
        carry = parts[0]
        for following in parts[1:]:
            if _SENTENCE_END.search(carry):
                result.append(carry)
                carry = following
            else:
                carry = carry.rstrip() + " " + following.lstrip()
        result.append(carry)
        return "\n\n".join(result)

    lease_text = _resolve_page_breaks(lease_text)

    chunks = [c.strip() for c in lease_text.split("\n\n")]
    chunks = [c for c in chunks if len(c) >= _MIN_CHUNK_CHARS]

    if len(chunks) < _MIN_CHUNKS and len(lease_text) > _LARGE_TEXT:
        expanded: list[str] = []
        for chunk in chunks:
            if len(chunk) > _OVERSIZED_CHUNK:
                sub = [sc.strip() for sc in chunk.split("\n")]
                expanded.extend(sub)
            else:
                expanded.append(chunk)
        chunks = [c for c in expanded if len(c) >= _MIN_CHUNK_CHARS]

    if len(chunks) < _MIN_CHUNKS and len(lease_text) > _LARGE_TEXT:
        print(
            f"  [WARN] Only {len(chunks)} chunks produced from a "
            f"{len(lease_text):,}-character lease. Chunking may have failed to "
            "find real structure -- retrieval quality will likely suffer."
        )

    return chunks


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed a list of text chunks using the module-level sentence-transformer."""
    return MODEL.encode(chunks).tolist()


def retrieve_candidates_for_chunk(
    conn,
    chunk_embedding: list[float],
    top_k: int = 8,
) -> list[dict]:
    """Find the top-k most semantically similar active requirements for one chunk."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT jurisdiction, requirement_key, summary, citation, check_tier
            FROM legal_sources
            WHERE status = 'active'
            ORDER BY embedding <=> %(vec)s::vector
            LIMIT %(k)s
            """,
            {"vec": chunk_embedding, "k": top_k},
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return [dict(zip(columns, row)) for row in rows]


def build_requirement_candidate_map(
    conn,
    chunks: list[str],
    chunk_embeddings: list[list[float]],
    top_k: int = 8,
) -> dict[str, list[str]]:
    """Invert per-chunk retrieval results into a requirement -> chunk text mapping."""
    candidate_map: dict[str, list[str]] = {}

    for chunk, embedding in zip(chunks, chunk_embeddings):
        candidates = retrieve_candidates_for_chunk(conn, embedding, top_k)
        for row in candidates:
            key = row["requirement_key"]
            if key not in candidate_map:
                candidate_map[key] = []
            if chunk not in candidate_map[key]:
                candidate_map[key].append(chunk)

    return candidate_map


def get_all_active_requirements(conn) -> dict[str, Requirement]:
    """Query all active requirements from legal_sources, keyed by requirement_key."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT jurisdiction, requirement_key, summary, citation, check_tier
            FROM legal_sources
            WHERE status = 'active'
            ORDER BY jurisdiction, requirement_key
            """
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return {
        row_dict["requirement_key"]: row_dict
        for row_dict in (dict(zip(columns, row)) for row in rows)
    }


def _delete_existing_clauses(conn, lease_id: str) -> None:
    """Delete any previously stored clause classifications for this lease_id."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM lease_clauses WHERE lease_id = %s", (lease_id,))


def _insert_classifications(
    conn,
    lease_id: str,
    classifications: list[Classification],
) -> None:
    """Bulk-insert validated classification entries into lease_clauses."""
    if not classifications:
        return

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO lease_clauses
                (lease_id, requirement_key, clause_text, confidence)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    lease_id,
                    c["requirement_key"],
                    c.get("matched_clause_text"),
                    c["confidence"],
                )
                for c in classifications
            ],
        )


def _normalize_for_comparison(s: str) -> str:
    """Normalise a string for loose substring matching against PDF-extracted text."""
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\s+([,.;])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_all_whitespace(s: str) -> str:
    """Apply punctuation normalisation then remove every whitespace character."""
    s = _normalize_for_comparison(s)
    return re.sub(r"\s+", "", s)


def _validate_classification(
    entry: Any,
    expected_keys: set[str],
    candidate_chunks_by_key: dict[str, list[str]],
    batch_label: str,
    batch_all_chunks: list[str],
) -> Classification | None:
    """Validate one classification entry returned by Claude."""
    if not isinstance(entry, dict):
        print(f"  [WARN] {batch_label}: skipping non-dict entry: {entry!r}")
        return None

    key = entry.get("requirement_key")
    addressed = entry.get("addressed")
    matched_text = entry.get("matched_clause_text")
    confidence = entry.get("confidence")

    if not isinstance(key, str) or not key:
        print(
            f"  [WARN] {batch_label}: skipping entry with missing/invalid "
            f"requirement_key: {entry!r}"
        )
        return None

    if key not in expected_keys:
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- not in the set of "
            "requirement_keys sent to Claude for this batch "
            "(hallucinated or mistyped key)."
        )
        return None

    if not isinstance(addressed, bool):
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- 'addressed' must be "
            f"boolean, got {addressed!r}"
        )
        return None

    if confidence is None or not isinstance(confidence, (int, float)):
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- 'confidence' must be "
            f"a number, got {confidence!r}"
        )
        return None

    original_confidence = float(confidence)
    clamped = max(0.0, min(1.0, original_confidence))
    if clamped != original_confidence:
        print(
            f"  [WARN] {batch_label}: '{key}' confidence {original_confidence} "
            f"clamped to {clamped}"
        )
    confidence = clamped

    if not addressed and matched_text is not None:
        print(
            f"  [WARN] {batch_label}: '{key}' addressed=false but "
            "matched_clause_text is not null -- clearing it."
        )
        matched_text = None

    if addressed and matched_text is not None:
        norm_match   = _normalize_for_comparison(matched_text).lower()
        strip_match  = _strip_all_whitespace(matched_text).lower()

        per_key_chunks  = candidate_chunks_by_key.get(key, [])
        norm_per_key    = [_normalize_for_comparison(c).lower() for c in per_key_chunks]
        strip_per_key   = [_strip_all_whitespace(c).lower()     for c in per_key_chunks]
        norm_batch_all  = [_normalize_for_comparison(c).lower() for c in batch_all_chunks]
        strip_batch_all = [_strip_all_whitespace(c).lower()     for c in batch_all_chunks]

        found_7a = any(norm_match in nc for nc in norm_per_key)
        found_7b = not found_7a and any(strip_match in sc for sc in strip_per_key)
        found_7c = not found_7a and not found_7b and any(
            norm_match in nc for nc in norm_batch_all
        )
        found_7d = not found_7a and not found_7b and not found_7c and any(
            strip_match in sc for sc in strip_batch_all
        )

        if found_7b:
            print(
                f"  [INFO] {batch_label}: '{key}' matched only via whitespace-stripped "
                "comparison (per-key candidates) -- likely a pypdf dropped-space "
                "artefact at a line-wrap boundary, not a fabrication."
            )
        elif found_7c:
            print(
                f"  [INFO] {batch_label}: '{key}' matched only in batch-wide chunk "
                "union (not in this key's own candidates) -- model drew on a chunk "
                "retrieved for a different requirement in the same batch."
            )
        elif found_7d:
            print(
                f"  [INFO] {batch_label}: '{key}' matched via whitespace-stripped "
                "comparison against the batch-wide chunk union -- pypdf dropped-space "
                "artefact across a cross-batch chunk."
            )
        elif not found_7a:
            import difflib

            print("[DEBUG-SUBSTRING-MISMATCH] ----------------------------------------")
            print(f"[DEBUG-SUBSTRING-MISMATCH] key:            {key!r}")
            print(f"[DEBUG-SUBSTRING-MISMATCH] batch:          {batch_label}")
            print(f"[DEBUG-SUBSTRING-MISMATCH] normalized_match repr:")
            print(f"[DEBUG-SUBSTRING-MISMATCH]   {norm_match!r}")
            print(f"[DEBUG-SUBSTRING-MISMATCH] normalized per-key chunks ({len(norm_per_key)} total):")
            for i, nc in enumerate(norm_per_key):
                print(f"[DEBUG-SUBSTRING-MISMATCH]   [{i}] {nc!r}")

            all_norm_chunks = norm_per_key or norm_batch_all
            if all_norm_chunks:
                ratios = [
                    difflib.SequenceMatcher(None, norm_match, nc).ratio()
                    for nc in all_norm_chunks
                ]
                best_idx = ratios.index(max(ratios))
                best_ratio = ratios[best_idx]
                print(
                    f"[DEBUG-SUBSTRING-MISMATCH] best SequenceMatcher ratio: "
                    f"{best_ratio:.4f} (candidate [{best_idx}])"
                )
                diff_lines = list(difflib.unified_diff(
                    norm_match.splitlines(keepends=True),
                    all_norm_chunks[best_idx].splitlines(keepends=True),
                    fromfile="matched_clause_text",
                    tofile=f"candidate[{best_idx}]",
                ))[:10]
                if diff_lines:
                    print("[DEBUG-SUBSTRING-MISMATCH] diff snippet (first 10 lines):")
                    for line in diff_lines:
                        print(f"[DEBUG-SUBSTRING-MISMATCH]   {line}", end="")
                    print()

            print("[DEBUG-SUBSTRING-MISMATCH] ----------------------------------------")
            print(
                f"  [WARN] {batch_label}: '{key}' matched_clause_text does not "
                "appear as a substring of any retrieved candidate chunk -- "
                "model may have invented or paraphrased text not present in "
                "the retrieved excerpts."
            )

    return {
        "requirement_key": key,
        "addressed": addressed,
        "matched_clause_text": matched_text,
        "confidence": confidence,
    }


def classify_with_candidates(
    requirements_with_candidates: dict[str, dict],
) -> list[Classification]:
    """Classify requirements that have retrieval candidates using Claude."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    all_keys = list(requirements_with_candidates.keys())
    batches = [
        all_keys[i : i + _BATCH_SIZE] for i in range(0, len(all_keys), _BATCH_SIZE)
    ]
    total_batches = len(batches)
    all_results: list[Classification] = []

    for batch_idx, batch_keys in enumerate(batches, start=1):
        batch_label = f"batch {batch_idx}/{total_batches}"
        expected_keys = set(batch_keys)

        sections: list[str] = []
        for key in batch_keys:
            req = requirements_with_candidates[key]
            chunks = req.get("candidate_chunks", [])
            chunk_lines = "\n".join(
                f"  [{i + 1}] {chunk}" for i, chunk in enumerate(chunks)
            )
            sections.append(
                f"REQUIREMENT: {key}\n"
                f"Topic: {req['summary']}\n"
                f"Candidate excerpts retrieved from the lease:\n{chunk_lines}"
            )

        prompt = (
            "You are reviewing a lease document for specific legal topics.\n\n"
            "For each REQUIREMENT below, candidate excerpts have been retrieved "
            "from the lease using semantic similarity search. IMPORTANT: these "
            "excerpts were retrieved by semantic similarity and may not actually "
            "be relevant -- confirm whether any of them genuinely addresses this "
            "topic rather than assuming a retrieved candidate is automatically a "
            "match.\n\n"
            "Your task is ONLY to determine whether each topic is addressed in "
            "the lease and, if so, quote the relevant lease text verbatim. Do "
            "NOT assess legal compliance -- only report presence or absence.\n\n"
            + "\n\n".join(sections)
            + "\n\nCall record_compliance_classifications with one entry per "
            "REQUIREMENT listed above."
        )

        print(f"  [{batch_label}] Classifying {len(batch_keys)} requirements ...")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                tools=[_RECORD_COMPLIANCE_CLASSIFICATIONS_TOOL],
                tool_choice={
                    "type": "tool",
                    "name": "record_compliance_classifications",
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            failed_keys_str = ", ".join(sorted(batch_keys))
            print(
                f"  [ERROR] {batch_label}: Anthropic API call failed -- {exc}\n"
                f"  Failed requirement_keys: {failed_keys_str}"
            )
            for key in batch_keys:
                all_results.append({
                    "requirement_key": key,
                    "addressed": False,
                    "matched_clause_text": None,
                    "confidence": -1.0,
                    "classification_error": True,
                })
            continue

        tool_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_block is None:
            failed_keys_str = ", ".join(sorted(batch_keys))
            print(
                f"  [ERROR] {batch_label}: no tool_use block in response.\n"
                f"  Failed requirement_keys: {failed_keys_str}"
            )
            for key in batch_keys:
                all_results.append({
                    "requirement_key": key,
                    "addressed": False,
                    "matched_clause_text": None,
                    "confidence": -1.0,
                    "classification_error": True,
                })
            continue

        raw_entries: list[Any] = tool_block.input.get("classifications", [])

        candidate_chunks_by_key = {
            key: requirements_with_candidates[key].get("candidate_chunks", [])
            for key in batch_keys
        }

        seen: set[str] = set()
        batch_all_chunks: list[str] = []
        for key in batch_keys:
            for chunk in requirements_with_candidates[key].get("candidate_chunks", []):
                if chunk not in seen:
                    seen.add(chunk)
                    batch_all_chunks.append(chunk)

        validated: list[Classification] = []
        for entry in raw_entries:
            result = _validate_classification(
                entry, expected_keys, candidate_chunks_by_key, batch_label,
                batch_all_chunks,
            )
            if result is not None:
                validated.append(result)

        returned_keys = {c["requirement_key"] for c in validated}
        missing = expected_keys - returned_keys
        if missing:
            print(
                f"  [WARN] {batch_label}: Claude did not return entries for: "
                + ", ".join(sorted(missing))
            )

        all_results.extend(validated)

    return all_results


def parse_lease(lease_text: str, lease_id: str | None = None) -> str:
    """Parse a lease document against all active legal requirements."""
    if lease_id is None:
        lease_id = str(uuid.uuid4())

    print(f"Parsing lease {lease_id} ...")

    print("Chunking lease text ...")
    chunks = chunk_lease_text(lease_text)
    print(f"  {len(chunks)} chunks produced.")

    print("Embedding chunks ...")
    chunk_embeddings = embed_chunks(chunks)

    conn = get_connection()

    try:
        print("Building retrieval candidate map ...")
        candidate_map = build_requirement_candidate_map(
            conn, chunks, chunk_embeddings
        )

        all_requirements = get_all_active_requirements(conn)
        total_requirements = len(all_requirements)
        print(f"Found {total_requirements} active requirements.")

        _delete_existing_clauses(conn, lease_id)

        no_candidate_keys = [k for k in all_requirements if k not in candidate_map]
        has_candidate_keys = [k for k in all_requirements if k in candidate_map]

        print(
            f"  {len(has_candidate_keys)} requirements have retrieval candidates "
            "(will be sent for LLM classification)."
        )
        print(
            f"  {len(no_candidate_keys)} requirements have no candidates anywhere "
            "in the lease (marked absent directly, no LLM call)."
        )

        no_candidate_entries: list[Classification] = [
            {
                "requirement_key": k,
                "addressed": False,
                "matched_clause_text": None,
                "confidence": 0.85,
            }
            for k in no_candidate_keys
        ]
        _insert_classifications(conn, lease_id, no_candidate_entries)

        requirements_with_candidates: dict[str, dict] = {
            key: {
                **all_requirements[key],
                "candidate_chunks": candidate_map[key],
            }
            for key in has_candidate_keys
        }

        print(
            f"\nSending {len(has_candidate_keys)} requirements for LLM "
            "classification ..."
        )
        llm_results = classify_with_candidates(requirements_with_candidates)
        _insert_classifications(conn, lease_id, llm_results)

        addressed_count = sum(
            1 for r in llm_results
            if r.get("addressed") and not r.get("classification_error")
        )
        failed_entries = [r for r in llm_results if r.get("classification_error")]
        failed_count = len(failed_entries)
        failed_key_names = [r["requirement_key"] for r in failed_entries]

        print(f"\n{'=' * 60}")
        print(f"Summary for lease {lease_id}:")
        print(f"  Total active requirements:          {total_requirements}")
        print(f"  Skipped via retrieval (no match):   {len(no_candidate_keys)}")
        print(f"  Sent for LLM classification:        {len(has_candidate_keys)}")
        print(f"  Addressed (LLM confirmed):          {addressed_count}")
        if failed_count:
            print(f"  Failed to classify (API error):     {failed_count}")
            print(f"    Failed keys: {', '.join(sorted(failed_key_names))}")
        print(f"{'=' * 60}")

    finally:
        conn.close()

    return lease_id


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python agents/lease_parser.py <path-to-lease-file>")
        sys.exit(1)

    from agents.document_extract import extract_text

    file_path = sys.argv[1]
    text = extract_text(file_path)
    print(f"Extracted {len(text):,} characters from {file_path}\n")

    result_id = parse_lease(text)
    print(f"\nLease stored with ID: {result_id}")
