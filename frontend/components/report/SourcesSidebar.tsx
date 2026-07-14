import type { Report } from "@/types/report";

interface SourceEntry {
  citation: string;
  source_url: string | null;
  jurisdiction: string;
}

interface SourcesSidebarProps {
  report: Report;
}

export default function SourcesSidebar({ report }: SourcesSidebarProps) {
  // Collect every {citation, source_url, jurisdiction} from BOTH requirement
  // findings (flattened across all groups) AND awareness items.
  // Deduplicated BY CITATION TEXT -- not by source_url, because distinct
  // citations like "68 P.S. Section 201" and "202" can share the same URL
  // (different sections within one PDF). Deduplicating by URL would silently
  // collapse real distinct citations into one entry.
  const seenCitations = new Set<string>();
  const allSources: SourceEntry[] = [];

  for (const group of report.requirement_findings) {
    for (const finding of group.findings) {
      if (!seenCitations.has(finding.citation)) {
        seenCitations.add(finding.citation);
        allSources.push({
          citation: finding.citation,
          source_url: finding.source_url,
          jurisdiction: finding.jurisdiction,
        });
      }
    }
  }
  for (const item of report.awareness_items) {
    if (!seenCitations.has(item.citation)) {
      seenCitations.add(item.citation);
      allSources.push({
        citation: item.citation,
        source_url: item.source_url,
        jurisdiction: item.jurisdiction,
      });
    }
  }

  // Group by jurisdiction, sort entries within each jurisdiction by citation.
  const byJurisdiction = new Map<string, SourceEntry[]>();
  for (const entry of allSources) {
    const group = byJurisdiction.get(entry.jurisdiction) ?? [];
    group.push(entry);
    byJurisdiction.set(entry.jurisdiction, group);
  }
  for (const [, entries] of byJurisdiction) {
    entries.sort((a, b) => a.citation.localeCompare(b.citation));
  }
  const jurisdictions = Array.from(byJurisdiction.keys()).sort();

  return (
    <div
      style={{
        position: "sticky",
        top: 24,
        alignSelf: "flex-start",
        width: 240,
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: "var(--accent-bg)",
          padding: "12px 16px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-fraunces)",
            fontSize: 15,
            fontWeight: 600,
            color: "var(--accent)",
            margin: "0 0 2px",
          }}
        >
          Sources
        </p>
        <p
          style={{
            fontFamily: "var(--font-inter)",
            fontSize: 11,
            color: "var(--text-secondary)",
            margin: 0,
          }}
        >
          {allSources.length} citation{allSources.length === 1 ? "" : "s"}
        </p>
      </div>

      {/* Source list grouped by jurisdiction */}
      <div
        style={{
          border: "1px solid var(--border)",
          borderTop: "none",
          borderRadius: "0 0 8px 8px",
          overflow: "hidden",
        }}
      >
        {jurisdictions.map((jurisdiction, ji) => (
          <div key={jurisdiction}>
            <p
              style={{
                fontFamily: "var(--font-inter)",
                fontSize: 10,
                fontWeight: 600,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                padding: "8px 14px 4px",
                margin: 0,
                borderTop: ji === 0 ? "none" : "1px solid var(--border)",
                backgroundColor: "var(--surface-2)",
              }}
            >
              {jurisdiction}
            </p>
            {(byJurisdiction.get(jurisdiction) ?? []).map((entry, i) => (
              <div
                key={entry.citation}
                style={{
                  padding: "7px 14px",
                  borderTop: "1px solid var(--border)",
                }}
              >
                {entry.source_url ? (
                  <a
                    href={entry.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: "none" }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-ibm-plex-mono)",
                        fontSize: 11,
                        color: "var(--accent)",
                        textDecoration: "underline",
                        textUnderlineOffset: 2,
                      }}
                    >
                      {entry.citation}
                    </span>
                  </a>
                ) : (
                  <span
                    style={{
                      fontFamily: "var(--font-ibm-plex-mono)",
                      fontSize: 11,
                      color: "var(--text-muted)",
                    }}
                  >
                    {entry.citation}
                  </span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
