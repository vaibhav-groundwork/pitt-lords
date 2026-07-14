"use client";

import { useEffect, useState } from "react";

interface Fact {
  headline: string;
  body: string;
  citation: string;
}

const ALL_FACTS: Fact[] = [
  {
    headline: "Pittsburgh requires a rental permit",
    body: "Renting without one is a summary offense, up to $500 per unit, per month, until you register.",
    citation: "Pittsburgh Code § 781.02, 781.09",
  },
  {
    headline: "Pre-1978 units need a lead warning, in the lease itself",
    body: "The federal Lead Warning Statement has to be attached to or included in the lease, not handed over separately.",
    citation: "42 U.S.C. § 4852d",
  },
  {
    headline: "City fair housing rules go further than federal law",
    body: "Pittsburgh also protects against discrimination based on sexual orientation, gender identity, and hairstyle.",
    citation: "Pittsburgh Code § 659.03",
  },
  {
    headline: "Detector batteries have a default split",
    body: "You supply the first battery at move-in, then the tenant keeps smoke and CO detectors working after that.",
    citation: "Article VI § 643",
  },
  {
    headline: "Tenants can make reasonable modifications for disabilities",
    body: "Federal law lets tenants with disabilities make reasonable physical changes to the unit at their own expense. You can require the unit be restored to its original condition when they move out.",
    citation: "42 U.S.C. § 3604(f)(3)(A)",
  },
  {
    headline: "A deceased tenant's estate controls the lease, not you",
    body: "The law gives the estate's executor up to two months (or 14 days after they act) to decide whether to end the lease. It can't simply be treated as automatically abandoned.",
    citation: "68 P.S. Section 514(a)",
  },
  {
    headline: "You can't dispose of a tenant's belongings without permission",
    body: "Even after a lease ends, you generally can't touch property left behind unless the unit is genuinely abandoned and you follow the required notice steps.",
    citation: "68 P.S. Section 505.1(f)",
  },
  {
    headline: "Tenants can pick their own repair people",
    body: "The law protects a tenant's right to invite tradespeople and service providers of their choosing. A lease can't hand that choice entirely to the landlord.",
    citation: "68 P.S. Section 504-A",
  },
];

const SESSION_KEY = "pittlords_did_you_know_indices";

function pickRandomIndices(): number[] {
  const indices = Array.from({ length: ALL_FACTS.length }, (_, i) => i);
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  return indices.slice(0, 4);
}

export default function DidYouKnowFacts() {
  const [pickedFacts, setPickedFacts] = useState<Fact[]>([]);

  useEffect(() => {
    let indices: number[];
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (stored) {
      try {
        indices = JSON.parse(stored) as number[];
      } catch {
        indices = pickRandomIndices();
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(indices));
      }
    } else {
      indices = pickRandomIndices();
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(indices));
    }
    setPickedFacts(indices.map((i) => ALL_FACTS[i]));
  }, []);

  if (pickedFacts.length === 0) return null;

  return (
    <div style={{ marginTop: "auto", borderTop: "1px solid var(--border)" }}>
      <div
        style={{
          backgroundColor: "var(--accent-bg)",
          padding: "18px 20px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <p style={{ fontSize: 18, fontFamily: "var(--font-fraunces)", fontWeight: 600, color: "var(--accent)", margin: "0 0 3px" }}>
          Did you know?
        </p>
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: 0 }}>
          A few things Pittsburgh landlords often miss
        </p>
      </div>
      <div>
        {pickedFacts.map((fact, i) => (
          <div
            key={fact.headline}
            style={{
              padding: "13px 20px",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            <p style={{ fontSize: 12.5, fontWeight: 600, margin: "0 0 4px", color: "var(--text-primary)" }}>{fact.headline}</p>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, margin: "0 0 5px" }}>{fact.body}</p>
            <p style={{ fontFamily: "var(--font-ibm-plex-mono)", fontSize: 10, color: "var(--text-muted)", margin: 0 }}>{fact.citation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
