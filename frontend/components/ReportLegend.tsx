const LEGEND_ITEMS = [
  {
    color: "var(--green)",
    label: "Compliant",
    description: "Your lease clause matches what the law requires.",
  },
  {
    color: "var(--red)",
    label: "Contradicts",
    description: "Your lease conflicts with a legal requirement, worth addressing.",
  },
  {
    color: "var(--amber)",
    label: "Needs review",
    description: "The match is unclear or partial, worth a closer look.",
  },
  {
    color: "var(--gray)",
    label: "Not addressed",
    description: "Your lease doesn't mention this topic at all.",
  },
  {
    color: "var(--violet)",
    label: "Flagged by reviewer",
    description:
      "A second AI reviewer double-checked this finding and flagged it for extra attention.",
  },
];

export default function ReportLegend() {
  return (
    <div>
      <div
        style={{
          backgroundColor: "var(--accent-bg)",
          padding: "10px 16px",
          borderRadius: 6,
          marginBottom: 16,
        }}
      >
        <p
          style={{
            fontSize: 18,
            fontFamily: "var(--font-fraunces)",
            fontWeight: 600,
            color: "var(--accent)",
            marginBottom: 2,
          }}
        >
          Reading your report
        </p>
        <p
          style={{
            fontSize: 11.5,
            fontFamily: "var(--font-inter)",
            color: "var(--text-secondary)",
          }}
        >
          What each finding status means
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {LEGEND_ITEMS.map((item, i) => (
          <div
            key={item.label}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: "10px 16px",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            <div
              style={{
                flexShrink: 0,
                width: 9,
                height: 9,
                borderRadius: "50%",
                backgroundColor: item.color,
                marginTop: 4,
              }}
            />
            <div>
              <p
                style={{
                  fontSize: 12.5,
                  fontFamily: "var(--font-inter)",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  marginBottom: 2,
                }}
              >
                {item.label}
              </p>
              <p
                style={{
                  fontSize: 12,
                  fontFamily: "var(--font-eb-garamond)",
                  color: "var(--text-secondary)",
                  lineHeight: 1.45,
                }}
              >
                {item.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
