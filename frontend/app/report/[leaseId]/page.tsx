"use client";

// Next.js 16: params is a Promise in Client Components -- must be unwrapped
// with React.use() (not await, which is only valid in async Server Components).
import { use } from "react";
import { useLeaseReport } from "@/hooks/useLeaseReport";
import ProcessingView from "@/components/report/ProcessingView";
import FailedView from "@/components/report/FailedView";
import ScoreCard from "@/components/report/ScoreCard";
import ProcessingWarningsBanner from "@/components/report/ProcessingWarningsBanner";
import FindingsFamilyGroup from "@/components/report/FindingsFamilyGroup";
import AwarenessSection from "@/components/report/AwarenessSection";
import SourcesSidebar from "@/components/report/SourcesSidebar";

export default function ReportPage({
  params,
}: {
  params: Promise<{ leaseId: string }>;
}) {
  const { leaseId } = use(params);
  const { status, report, errorMessage, notFound } = useLeaseReport(leaseId);

  // Terminal error states
  if (notFound || (status === "failed" && errorMessage !== null)) {
    return <FailedView errorMessage={errorMessage} notFound={notFound} />;
  }

  // Still processing (including the "loading" sentinel before first response)
  if (report === null) {
    return <ProcessingView status={status} />;
  }

  // Report is ready
  return (
    <div style={{ padding: "40px 32px 48px" }}>
      {/* Page heading */}
      <h1
        style={{
          fontFamily: "var(--font-fraunces)",
          fontWeight: 500,
          fontSize: 30,
          color: "var(--text-primary)",
          marginBottom: 6,
        }}
      >
        Lease compliance report
      </h1>
      <p
        style={{
          fontFamily: "var(--font-inter)",
          fontSize: 12,
          color: "var(--text-muted)",
          marginBottom: 24,
        }}
      >
        Generated {new Date(report.generated_at).toLocaleString()} &middot;{" "}
        <span style={{ fontFamily: "var(--font-ibm-plex-mono)" }}>
          {leaseId}
        </span>
      </p>

      {/* Score tiles */}
      <ScoreCard summary={report.summary} />

      {/* Processing warnings banner -- self-hides when all arrays are empty */}
      <ProcessingWarningsBanner warnings={report.processing_warnings} />

      {/* Report-specific disclaimer (in addition to the app-wide sticky one
          in the root layout, which is a persistent site-wide notice) */}
      <p
        style={{
          fontFamily: "var(--font-eb-garamond)",
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 28,
          fontStyle: "italic",
        }}
      >
        {report.disclaimer}
      </p>

      {/* Two-column body: main findings + sources sidebar */}
      <div
        style={{
          display: "flex",
          gap: 32,
          alignItems: "flex-start",
        }}
      >
        {/* Main column */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {report.requirement_findings.map((group) => (
            <FindingsFamilyGroup key={group.family_key} group={group} />
          ))}
          <AwarenessSection items={report.awareness_items} />
        </div>

        {/* Sources sidebar -- sticky panel, right column */}
        <SourcesSidebar report={report} />
      </div>
    </div>
  );
}
