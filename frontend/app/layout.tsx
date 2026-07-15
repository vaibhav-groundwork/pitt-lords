import type { Metadata, Viewport } from "next";
import {
  Fraunces,
  EB_Garamond,
  Inter,
  IBM_Plex_Mono,
} from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import Disclaimer from "@/components/Disclaimer";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fraunces",
  display: "swap",
});

const ebGaramond = EB_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-eb-garamond",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

// Separate from metadata per Next.js 14+ convention -- viewport must be its
// own export (the metadata.viewport field is deprecated). Required so @media
// queries match the device's real pixel width, not the ~980px virtual viewport
// mobile browsers use when no explicit viewport meta tag is present.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "Pitt-Lords",
  description:
    "Lease compliance checklist for Pittsburgh-area landlords. Upload your lease and see exactly where it stands against Pittsburgh, Allegheny County, Pennsylvania, and federal law.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${ebGaramond.variable} ${inter.variable} ${ibmPlexMono.variable}`}
    >
      <body
        className="app-shell"
        style={{
          display: "flex",
          minHeight: "100vh",
          fontFamily: "var(--font-inter)",
        }}
      >
        <Sidebar />

        {/* Main region: flex-1 so it fills remaining width */}
        <div
          style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
          }}
        >
          {/* Mobile-only notice: hidden on desktop via .mobile-notice base rule,
              revealed on narrow screens by the @media (max-width: 768px) override
              in globals.css. Not a hard gate -- purely informational given the
              density of the compliance report content. Distinct from and unrelated
              to the sticky <Disclaimer /> at the bottom of this same container. */}
          <div
            className="mobile-notice"
            style={{
              backgroundColor: "var(--accent-bg)",
              color: "var(--accent)",
              fontFamily: "var(--font-inter)",
              fontSize: 12.5,
              textAlign: "center",
              padding: "10px 20px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            For the best experience reviewing detailed compliance reports, we
            recommend using Pitt-Lords on a desktop or tablet.
          </div>

          <main style={{ flex: 1 }}>{children}</main>
          {/* Disclaimer is the last child so sticky bottom works correctly */}
          <Disclaimer />
        </div>
      </body>
    </html>
  );
}
