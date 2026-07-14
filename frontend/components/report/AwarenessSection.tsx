import type { AwarenessItem } from "@/types/report";

interface AwarenessSectionProps {
  items: AwarenessItem[];
}

export default function AwarenessSection({ items }: AwarenessSectionProps) {
  if (items.length === 0) return null;

  return (
    <div style={{ marginTop: 36 }}>
      <h2
        style={{
          fontFamily: "var(--font-fraunces)",
          fontSize: 22,
          fontWeight: 500,
          color: "var(--text-primary)",
          marginBottom: 6,
        }}
      >
        Also worth knowing
      </h2>
      <p
        style={{
          fontFamily: "var(--font-eb-garamond)",
          fontSize: 16,
          color: "var(--text-secondary)",
          lineHeight: 1.55,
          marginBottom: 20,
        }}
      >
        Your lease doesn&apos;t address these topics, but they&apos;re part of
        the legal landscape every Pittsburgh landlord should be aware of.
      </p>

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: 10,
          overflow: "hidden",
        }}
      >
        {items.map((item, i) => (
          <div
            key={item.citation}
            style={{
              padding: "14px 20px",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            {/* Citation -- linked if source_url present */}
            {item.source_url ? (
              <a
                href={item.source_url}
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
                    display: "block",
                    marginBottom: 5,
                  }}
                >
                  {item.citation}
                </span>
              </a>
            ) : (
              <span
                style={{
                  fontFamily: "var(--font-ibm-plex-mono)",
                  fontSize: 11.5,
                  color: "var(--text-muted)",
                  display: "block",
                  marginBottom: 5,
                }}
              >
                {item.citation}
              </span>
            )}

            <p
              style={{
                fontFamily: "var(--font-eb-garamond)",
                fontSize: 15.5,
                color: "var(--text-primary)",
                lineHeight: 1.55,
                margin: 0,
              }}
            >
              {item.summary}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
