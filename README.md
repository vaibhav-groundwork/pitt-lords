# Pitt-Lords

A lease compliance checklist assistant for landlords renting in Pittsburgh, PA.

## What this is (and isn't)

Pitt-Lords checks an uploaded lease against known Pennsylvania state statute
and City of Pittsburgh ordinance requirements (security deposits, notice
periods, required disclosures) and reports specific, citable findings.

**This is not legal advice, and it does not certify compliance.** Every
finding shown to the user includes the exact source text and citation it was
checked against, so the landlord (or their attorney) can verify the reasoning
directly. Anything the system can't confirm with high confidence is flagged
as "needs manual review" rather than presented as a verdict.

## Status

Early build -- see `docs/build-plan.md` for the phased plan this repo follows.

## Local setup

1. `cp .env.example .env` and fill in your Anthropic API key.
2. `docker compose up -d` -- starts Postgres with pgvector, runs the schema
   in `ingestion/sql/001_init.sql` automatically on first start.
3. `python -m venv venv && source venv/bin/activate`
4. `pip install -r requirements.txt`
5. `uvicorn api.main:app --reload`
6. Confirm it's alive: `curl http://localhost:8000/health`

## Repo structure

```
data/         raw source text as retrieved, before structuring
ingestion/    SQL schema, chunking/tagging scripts, KB build
agents/       lease-parser, compliance-diff, verifier agents
api/          FastAPI backend
eval/         test leases + precision/recall scoring
frontend/     Next.js app (scaffolded separately)
docs/         architecture notes, source-of-record table, case study
```
