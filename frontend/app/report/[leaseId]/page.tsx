interface ReportPageProps {
  params: Promise<{ leaseId: string }>;
}

export default async function ReportPage({ params }: ReportPageProps) {
  const { leaseId } = await params;

  return (
    <div
      style={{
        padding: "48px 40px",
        fontFamily: "var(--font-eb-garamond)",
        color: "var(--text-secondary)",
        fontSize: 17,
      }}
    >
      <p>Report page coming soon.</p>
      <p
        style={{
          marginTop: 8,
          fontSize: 13,
          fontFamily: "var(--font-ibm-plex-mono)",
          color: "var(--text-muted)",
        }}
      >
        lease_id: {leaseId}
      </p>
    </div>
  );
}
