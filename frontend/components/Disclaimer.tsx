export default function Disclaimer() {
  return (
    <div
      className="no-print"
      style={{
        position: "sticky",
        bottom: 0,
        backgroundColor: "var(--accent-bg)",
        borderTop: "1px solid var(--border)",
        padding: "12px 32px",
        display: "flex",
        alignItems: "flex-start",
        gap: "10px",
        zIndex: 10,
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 18,
          height: 18,
          borderRadius: "50%",
          border: "1.5px solid var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginTop: 1,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--accent)",
            lineHeight: 1,
            fontFamily: "var(--font-inter)",
          }}
        >
          i
        </span>
      </div>
      <p
        style={{
          fontSize: 12.5,
          color: "var(--text-secondary)",
          lineHeight: 1.5,
          fontFamily: "var(--font-eb-garamond)",
        }}
      >
        <strong style={{ color: "var(--accent)", fontWeight: 600 }}>
          Not legal advice.
        </strong>{" "}
        Pitt-Lords is a quick compliance checklist for Pittsburgh-area leases,
        meant to flag what&apos;s worth a closer look. It doesn&apos;t replace
        reviewing your lease with a licensed attorney before you act on anything
        below.
      </p>
    </div>
  );
}
