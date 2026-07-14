import type { FamilyGroup } from "@/types/report";
import FindingCard from "./FindingCard";

interface FindingsFamilyGroupProps {
  group: FamilyGroup;
}

export default function FindingsFamilyGroup({ group }: FindingsFamilyGroupProps) {
  // Fallback title: full citation of the first finding, not the bare family_key.
  // e.g. "68 P.S. Section 631" is readable; "631" alone is meaningless.
  const heading =
    group.friendly_title ?? group.findings[0]?.citation ?? group.family_key;

  return (
    <div
      style={{
        marginBottom: 20,
        border: "1px solid var(--border)",
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      {/* Tinted header band */}
      <div
        style={{
          backgroundColor: "var(--accent-bg)",
          padding: "12px 20px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-fraunces)",
            fontSize: 16,
            fontWeight: 600,
            color: "var(--accent)",
            margin: 0,
          }}
        >
          {heading}
        </p>
      </div>

      {/* Findings with divider lines, no per-finding individual card borders */}
      <div>
        {group.findings.map((finding, i) => (
          <div
            key={finding.requirement_key}
            style={{
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            <FindingCard finding={finding} />
          </div>
        ))}
      </div>
    </div>
  );
}
