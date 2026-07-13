# V2 Ideas (not in current scope)

Ideas worth pursuing later, deliberately kept out of the current build so
they don't extend the timeline or creep into the compliance-checker's scope.

---

## Lease builder (form-based intake -> generated lease), Pittsburgh only

Instead of only reviewing an uploaded lease, let a landlord fill out a
structured form (parties, address, rent, term, deposit amount, move-in date)
and generate a lease document that's compliant by construction, using the
same legal_sources table that powers the compliance checker as the source of
truth for what the generated lease must contain.

Rough effort estimate (Pittsburgh-only scope):
- Form intake + validation: 8-12 hrs
- Template logic pulling from legal_sources (pre-filled correct deposit
  caps by year, required disclosures, no invalid waiver language): 15-20 hrs
- Running the generated lease back through our own compliance-diff and
  verifier pipeline as a self-check before handing it to the user
  (non-negotiable if built, given the app checks other documents against
  these same rules): 5-8 hrs
- Document rendering to PDF/docx, two-stage export pattern like Groundwork's
  exporters (LLM plans structure, deterministic code renders): 10-15 hrs
- Total: roughly 40-55 hrs, about a third to half of the original build.

Why deferred: generation carries a different, likely higher liability
profile than review. A wrong compliance flag says "verify this yourself." A
wrong generated clause is something the landlord may use directly. This
deserves its own dedicated liability review (similar depth to the one we
did before choosing the review-only design), not a rushed add-on to the
current phase.

Good architectural story if pursued: same knowledge base powering both
generation and checking is a strong, non-obvious reuse worth showing in a
case study.
