// Stage progress is computed from the actual current status on every render --
// no local memory of prior stages -- so a page refresh mid-process shows
// accurate progress rather than resetting to step 1.

const STAGES: { key: string; label: string }[] = [
  { key: "extracting_text",      label: "Reading your lease document..." },
  { key: "parsing_clauses",      label: "Identifying relevant clauses..." },
  { key: "checking_compliance",  label: "Checking compliance against Pittsburgh, Allegheny County, PA, and federal law..." },
  { key: "verifying",            label: "Double-checking findings with a second AI reviewer..." },
];

interface ProcessingViewProps {
  status: string;
}

export default function ProcessingView({ status }: ProcessingViewProps) {
  // Index of the currently active stage. If status is "loading" or "uploaded"
  // (hook sentinel or first backend status before pipeline starts), this will
  // be -1, which renders all stages as pending -- correct and intentional.
  const currentIndex = STAGES.findIndex((s) => s.key === status);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "72px 32px 48px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 520 }}>
        <h1
          style={{
            fontFamily: "var(--font-fraunces)",
            fontWeight: 500,
            fontSize: 28,
            color: "var(--text-primary)",
            marginBottom: 8,
          }}
        >
          Reviewing your lease
        </h1>
        <p
          style={{
            fontFamily: "var(--font-eb-garamond)",
            fontSize: 17,
            color: "var(--text-secondary)",
            marginBottom: 40,
            lineHeight: 1.55,
          }}
        >
          This usually takes a minute or two. You can leave this page open
          while we work.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {STAGES.map((stage, i) => {
            const isDone = i < currentIndex;
            const isActive = i === currentIndex;
            const isPending = i > currentIndex;

            return (
              <div
                key={stage.key}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "14px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--border)",
                  opacity: isPending ? 0.4 : 1,
                  transition: "opacity 0.3s",
                }}
              >
                {/* Stage indicator */}
                <div
                  style={{
                    flexShrink: 0,
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    marginTop: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    backgroundColor: isDone
                      ? "var(--green)"
                      : isActive
                      ? "var(--accent)"
                      : "var(--surface-2)",
                    border: isPending ? "1.5px solid var(--border)" : "none",
                    // Pulsing ring for the active stage via box-shadow animation
                    // requires a keyframe -- use a simple solid fill + inner dot instead.
                  }}
                >
                  {isDone && (
                    <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                      <path
                        d="M2 5.5L4.5 8L9 3"
                        stroke="white"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                  {isActive && (
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        backgroundColor: "white",
                      }}
                    />
                  )}
                </div>

                <p
                  style={{
                    fontFamily: "var(--font-inter)",
                    fontSize: 14,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                    paddingTop: 2,
                    lineHeight: 1.45,
                  }}
                >
                  {stage.label}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
