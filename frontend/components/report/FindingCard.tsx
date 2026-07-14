import type { Finding } from "@/types/report";

// Status display labels and colors -- exact wording from ReportLegend.tsx
// so the report and the sidebar legend always say the same thing.
const STATUS_CONFIG: Record<
  Finding["status"],
  { label: string; color: string; bgColor: string }
> = {
  compliant: {
    label: "Compliant",
    color: "var(--green)",
    bgColor: "var(--green-bg)",
  },
  contradicts: {
    label: "Contradicts",
    color: "var(--red)",
    bgColor: "var(--red-bg)",
  },
  needs_review: {
    label: "Needs review",
    color: "var(--amber)",
    bgColor: "var(--amber-bg)",
  },
  absent: {
    label: "Not addressed",
    color: "var(--gray)",
    bgColor: "var(--gray-bg)",
  },
};

interface FindingCardProps {
  finding: Finding;
}

export default function FindingCard({ finding }: FindingCardProps) {
  const config = STATUS_CONFIG[finding.status];

  const citationNode = (
    <span
      style={{
        fontFamily: "var(--font-ibm-plex-mono)",
        fontSize: 11.5,
        color: "var(--text-secondary)",
      }}
    >
      {finding.citation}
    </span>
  );

  return (
    <div style={{ padding: "16px 20px" }}>
      {/* Citation + status badge row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        {/* Citation -- linked if source_url present, plain text otherwise */}
        {finding.source_url ? (
          <a
            href={finding.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: "none" }}
          >
            <span
              style={{
                fontFamily: "var(--font-ibm-plex-mono)",
                fontSize: 11.5,
                color: "var(--accent)",
                textDecoration: "underline",
                textUnderlineOffset: 2,
              }}
            >
              {finding.citation}
            </span>
          </a>
        ) : (
          citationNode
        )}

        {/* Status pill badge */}
        <span
          style={{
            fontFamily: "var(--font-inter)",
            fontSize: 11,
            fontWeight: 600,
            color: config.color,
            backgroundColor: config.bgColor,
            border: `1px solid ${config.color}`,
            borderRadius: 20,
            padding: "3px 9px",
            whiteSpace: "nowrap",
          }}
        >
          {config.label}
        </span>
      </div>

      {/* Explanation */}
      {finding.status === "absent" ? (
        finding.summary ? (
          <>
            <p
              style={{
                fontFamily: "var(--font-inter)",
                fontSize: 11.5,
                fontWeight: 600,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                marginBottom: 4,
              }}
            >
              What the law requires
            </p>
            <p
              style={{
                fontFamily: "var(--font-eb-garamond)",
                fontSize: 15.5,
                color: "var(--text-primary)",
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {finding.summary}
            </p>
          </>
        ) : (
          <p
            style={{
              fontFamily: "var(--font-eb-garamond)",
              fontSize: 15.5,
              color: "var(--text-primary)",
              lineHeight: 1.6,
              margin: 0,
            }}
          >
            {finding.explanation}
          </p>
        )
      ) : (
        <p
          style={{
            fontFamily: "var(--font-eb-garamond)",
            fontSize: 15.5,
            color: "var(--text-primary)",
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          {finding.explanation}
        </p>
      )}

      {/* Verifier flag callout -- only when verifier_flag is non-null */}
      {finding.verifier_flag !== null && (
        <div
          style={{
            marginTop: 12,
            borderLeft: "3px solid var(--violet)",
            backgroundColor: "var(--violet-bg)",
            borderRadius: "0 6px 6px 0",
            padding: "10px 14px",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-inter)",
              fontSize: 11.5,
              fontWeight: 600,
              color: "var(--violet)",
              margin: "0 0 4px",
            }}
          >
            Second opinion, flagged
          </p>
          <p
            style={{
              fontFamily: "var(--font-eb-garamond)",
              fontSize: 14.5,
              color: "var(--violet)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {finding.verifier_flag}
          </p>
        </div>
      )}
    </div>
  );
}
