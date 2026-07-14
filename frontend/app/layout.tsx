import type { Metadata } from "next";
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
          <main style={{ flex: 1 }}>{children}</main>
          {/* Disclaimer is the last child so sticky bottom works correctly */}
          <Disclaimer />
        </div>
      </body>
    </html>
  );
}
