import type { ProcessingWarnings } from "@/types/report";

interface ProcessingWarningsBannerProps {
  warnings: ProcessingWarnings;
}

export default function ProcessingWarningsBanner({
  warnings,
}: ProcessingWarningsBannerProps) {
  const { needs_reparse, never_parsed, compliance_judgment_failed } = warnings;

  const hasAny =
    needs_reparse.length > 0 ||
    never_parsed.length > 0 ||
    compliance_judgment_failed.length > 0;

  if (!hasAny) return null;

  const lines: string[] = [];
  if (needs_reparse.length > 0)
    lines.push(
      `${needs_reparse.length} requirement${needs_reparse.length === 1 ? "" : "s"} could not be automatically re-checked and may need manual review.`
    );
  if (never_parsed.length > 0)
    lines.push(
      `${never_parsed.length} requirement${never_parsed.length === 1 ? "" : "s"} were not processed for this lease.`
    );
  if (compliance_judgment_failed.length > 0)
    lines.push(
      `${compliance_judgment_failed.length} compliance check${compliance_judgment_failed.length === 1 ? "" : "s"} failed and need to be re-run.`
    );

  return (
    <div
      style={{
        backgroundColor: "var(--amber-bg)",
        border: "1.5px solid var(--amber)",
        borderRadius: 8,
        padding: "14px 18px",
        marginBottom: 28,
      }}
    >
      <p
        style={{
          fontFamily: "var(--font-inter)",
          fontSize: 13,
          fontWeight: 600,
          color: "var(--amber)",
          marginBottom: lines.length > 1 ? 8 : 0,
        }}
      >
        ⚠ This report may be incomplete
      </p>
      {lines.map((line) => (
        <p
          key={line}
          style={{
            fontFamily: "var(--font-eb-garamond)",
            fontSize: 14,
            color: "var(--amber)",
            lineHeight: 1.5,
            margin: "4px 0 0",
          }}
        >
          {line}
        </p>
      ))}
    </div>
  );
}
