"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "./Logo";
import DidYouKnowFacts from "./DidYouKnowFacts";
import ReportLegend from "./ReportLegend";

export default function Sidebar() {
  const pathname = usePathname();
  const isReportRoute = pathname?.startsWith("/report");

  return (
    <aside
      className="no-print"
      style={{
        width: 300,
        flexShrink: 0,
        height: "100vh",
        position: "sticky",
        top: 0,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "var(--surface)",
        borderRight: "1px solid var(--border)",
        overflowY: "auto",
        padding: "20px 16px",
        gap: 0,
      }}
    >
      {/* Back arrow — only on /report/* routes */}
      {isReportRoute && (
        <Link
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: 13,
            fontFamily: "var(--font-inter)",
            color: "var(--text-secondary)",
            marginBottom: 16,
            padding: "4px 2px",
            borderRadius: 4,
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLAnchorElement).style.color =
              "var(--text-primary)")
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLAnchorElement).style.color =
              "var(--text-secondary)")
          }
        >
          <span aria-hidden="true">←</span> Back
        </Link>
      )}

      {/* Brand block */}
      <Link
        href="/"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          marginBottom: 24,
          borderRadius: 6,
          padding: "4px 2px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Logo size={34} />
          <span
            style={{
              fontSize: 22,
              fontFamily: "var(--font-fraunces)",
              fontWeight: 500,
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}
          >
            Pitt-Lords
          </span>
        </div>
        <span
          style={{
            fontSize: 11.5,
            fontFamily: "var(--font-inter)",
            color: "var(--text-secondary)",
            paddingLeft: 2,
          }}
        >
          Compliance checklist for Pittsburgh landlords
        </span>
      </Link>

      {/* Route-dependent content */}
      {isReportRoute ? <ReportLegend /> : <DidYouKnowFacts />}
    </aside>
  );
}
