import Link from "next/link";

interface FailedViewProps {
  errorMessage: string | null;
  notFound?: boolean;
}

export default function FailedView({ errorMessage, notFound }: FailedViewProps) {
  const message = notFound
    ? "No lease found with this ID. It may have been removed or the link may be incorrect."
    : (errorMessage ?? "An unexpected error occurred.");

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
            marginBottom: 16,
          }}
        >
          Something went wrong
        </h1>

        <div
          style={{
            backgroundColor: "var(--red-bg)",
            border: "1px solid var(--red)",
            borderRadius: 8,
            padding: "16px 20px",
            marginBottom: 32,
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-eb-garamond)",
              fontSize: 16,
              color: "var(--red)",
              lineHeight: 1.55,
              margin: 0,
            }}
          >
            {message}
          </p>
        </div>

        <Link
          href="/"
          style={{
            display: "inline-block",
            fontFamily: "var(--font-inter)",
            fontSize: 14,
            fontWeight: 500,
            color: "var(--surface)",
            backgroundColor: "var(--accent)",
            borderRadius: 7,
            padding: "10px 22px",
            textDecoration: "none",
          }}
        >
          ← Try again
        </Link>
      </div>
    </div>
  );
}
