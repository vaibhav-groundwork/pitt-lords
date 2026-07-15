"use client";

import { useState } from "react";
import type { Report } from "@/types/report";

interface TileConfig {
  key: keyof Report["summary"];
  label: string;
  color: string;
  bgColor: string;
  tooltip: string;
}

const TILES: TileConfig[] = [
  {
    key: "compliant",
    label: "Compliant",
    color: "var(--green)",
    bgColor: "var(--green-bg)",
    tooltip: "Your lease clause matches what the law requires.",
  },
  {
    key: "contradicts",
    label: "Contradicts",
    color: "var(--red)",
    bgColor: "var(--red-bg)",
    tooltip: "Your lease conflicts with a legal requirement, worth addressing.",
  },
  {
    key: "needs_review",
    label: "Needs review",
    color: "var(--amber)",
    bgColor: "var(--amber-bg)",
    tooltip: "The match is unclear or partial, worth a closer look.",
  },
  {
    key: "absent",
    label: "Not addressed",
    color: "var(--gray)",
    bgColor: "var(--gray-bg)",
    tooltip: "Your lease doesn't mention this topic at all.",
  },
  {
    key: "disputed_by_verifier",
    label: "Flagged",
    color: "var(--violet)",
    bgColor: "var(--violet-bg)",
    tooltip: "A second AI reviewer double-checked these and flagged them for extra attention.",
  },
];

interface ScoreCardProps {
  summary: Report["summary"];
}

export default function ScoreCard({ summary }: ScoreCardProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  return (
    <div
      className="score-grid"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(5, 1fr)",
        gap: 10,
        marginBottom: 32,
      }}
    >
      {TILES.map((tile) => {
        const isHovered = hoveredKey === tile.key;
        return (
          <div
            key={tile.key}
            title={tile.tooltip}
            onMouseEnter={() => setHoveredKey(tile.key)}
            onMouseLeave={() => setHoveredKey(null)}
            style={{
              position: "relative",
              backgroundColor: tile.bgColor,
              border: `1.5px solid ${tile.color}`,
              borderRadius: 10,
              padding: "14px 12px",
              textAlign: "center",
              cursor: "default",
            }}
          >
            <p
              style={{
                fontFamily: "var(--font-fraunces)",
                fontSize: 28,
                fontWeight: 600,
                color: tile.color,
                margin: "0 0 4px",
                lineHeight: 1,
              }}
            >
              {summary[tile.key]}
            </p>
            <p
              style={{
                fontFamily: "var(--font-inter)",
                fontSize: 11.5,
                fontWeight: 500,
                color: tile.color,
                margin: 0,
                lineHeight: 1.3,
              }}
            >
              {tile.label}
            </p>

            {/* Custom hover tooltip -- title attr provides the accessible fallback */}
            {isHovered && (
              <div
                style={{
                  position: "absolute",
                  bottom: "calc(100% + 8px)",
                  left: "50%",
                  transform: "translateX(-50%)",
                  backgroundColor: "var(--text-primary)",
                  color: "var(--surface)",
                  fontFamily: "var(--font-inter)",
                  fontSize: 12,
                  lineHeight: 1.4,
                  padding: "7px 10px",
                  borderRadius: 6,
                  whiteSpace: "normal",
                  width: 180,
                  textAlign: "left",
                  zIndex: 20,
                  pointerEvents: "none",
                }}
              >
                {tile.tooltip}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
