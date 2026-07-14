"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ALLOWED_EXTENSIONS = new Set([".pdf", ".docx"]);

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot === -1 ? "" : filename.slice(dot).toLowerCase();
}

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "error"; message: string };

export default function HomePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ phase: "idle" });
  const [isDragOver, setIsDragOver] = useState(false);

  const isDisabled = uploadState.phase === "uploading";

  const handleFile = useCallback(
    async (file: File) => {
      const ext = getExtension(file.name);
      if (!ALLOWED_EXTENSIONS.has(ext)) {
        setUploadState({
          phase: "error",
          message: `"${file.name}" is not a supported file type. Please upload a .pdf or .docx file.`,
        });
        return;
      }

      setUploadState({ phase: "uploading" });

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch(`${API_URL}/leases`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          let detail = `Server error (${response.status}).`;
          try {
            const body = await response.json();
            if (body?.detail) detail = body.detail;
          } catch {
            // ignore JSON parse failure; use the fallback message above
          }
          setUploadState({ phase: "error", message: detail });
          return;
        }

        const data = await response.json();
        router.push(`/report/${data.lease_id}`);
      } catch {
        setUploadState({
          phase: "error",
          message:
            "Couldn't reach the server. Is the API running?",
        });
      }
    },
    [router]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragOver(false);
      if (isDisabled) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile, isDisabled]
  );

  const onDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (!isDisabled) setIsDragOver(true);
    },
    [isDisabled]
  );

  const onDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const onFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      // Reset input so the same file can be re-selected after an error
      e.target.value = "";
    },
    [handleFile]
  );

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        padding: "72px 32px 48px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 640 }}>
        {/* Heading */}
        <h1
          style={{
            fontFamily: "var(--font-fraunces)",
            fontWeight: 500,
            fontSize: 38,
            lineHeight: 1.2,
            color: "var(--text-primary)",
            marginBottom: 20,
          }}
        >
          Know where your lease stands, before a tenant ever does.
        </h1>

        {/* Lede */}
        <p
          style={{
            fontFamily: "var(--font-eb-garamond)",
            fontSize: 18,
            lineHeight: 1.65,
            color: "var(--text-secondary)",
            marginBottom: 48,
          }}
        >
          Upload your Pittsburgh rental lease and Pitt-Lords checks it against
          federal, Pennsylvania, Allegheny County, and City of Pittsburgh law,
          then shows you exactly what to look at, with citations back to the
          real source.
        </p>

        {/* Three steps — horizontal 3-column card grid; textAlign resets to left so card content isn't centered by the outer wrapper */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16,
            marginBottom: 48,
            textAlign: "left",
          }}
        >
          {[
            {
              n: "01",
              title: "Upload your lease",
              desc: "PDF or Word document, any standard residential lease.",
            },
            {
              n: "02",
              title: "Automated review",
              desc: "Checked clause by clause against 73 real legal requirements.",
            },
            {
              n: "03",
              title: "Get your report",
              desc: "Findings with citations, plus a second AI reviewer's sign-off.",
            },
          ].map(({ n, title, desc }) => (
            <div
              key={n}
              style={{
                backgroundColor: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: "18px",
              }}
            >
              <span
                style={{
                  display: "block",
                  fontFamily: "var(--font-ibm-plex-mono)",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--accent)",
                  marginBottom: 8,
                }}
              >
                {n}
              </span>
              <p
                style={{
                  fontFamily: "var(--font-fraunces)",
                  fontWeight: 600,
                  fontSize: 16,
                  color: "var(--text-primary)",
                  marginBottom: 6,
                }}
              >
                {title}
              </p>
              <p
                style={{
                  fontFamily: "var(--font-eb-garamond)",
                  fontSize: 15,
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                }}
              >
                {desc}
              </p>
            </div>
          ))}
        </div>

        {/* Upload dropzone */}
        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          style={{
            border: `2px dashed ${isDragOver ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 10,
            backgroundColor: isDragOver
              ? "var(--accent-bg)"
              : "var(--surface)",
            padding: "36px 24px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 14,
            transition: "border-color 0.15s, background-color 0.15s",
            cursor: isDisabled ? "default" : "pointer",
            opacity: isDisabled ? 0.7 : 1,
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-inter)",
              fontSize: 15,
              fontWeight: 500,
              color: isDragOver ? "var(--accent)" : "var(--text-secondary)",
              transition: "color 0.15s",
            }}
          >
            {uploadState.phase === "uploading"
              ? "Uploading…"
              : isDragOver
              ? "Drop to upload"
              : "Drop your lease here"}
          </p>

          {uploadState.phase !== "uploading" && (
            <>
              <p
                style={{
                  fontFamily: "var(--font-inter)",
                  fontSize: 13,
                  color: "var(--text-muted)",
                }}
              >
                or
              </p>

              <button
                disabled={isDisabled}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  fontFamily: "var(--font-inter)",
                  fontSize: 13.5,
                  fontWeight: 500,
                  color: "var(--surface)",
                  backgroundColor: "var(--accent)",
                  border: "none",
                  borderRadius: 6,
                  padding: "9px 20px",
                  cursor: isDisabled ? "default" : "pointer",
                  opacity: isDisabled ? 0.5 : 1,
                  transition: "opacity 0.15s",
                }}
              >
                Choose a file
              </button>

              <p
                style={{
                  fontFamily: "var(--font-inter)",
                  fontSize: 12,
                  color: "var(--text-muted)",
                }}
              >
                PDF or DOCX, up to 10 MB
              </p>
            </>
          )}

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            style={{ display: "none" }}
            onChange={onFileInputChange}
            disabled={isDisabled}
          />
        </div>

        {/* Error message */}
        {uploadState.phase === "error" && (
          <p
            style={{
              fontFamily: "var(--font-inter)",
              fontSize: 13,
              color: "var(--red)",
              marginTop: 10,
              lineHeight: 1.5,
            }}
          >
            {uploadState.message}
          </p>
        )}
      </div>
    </div>
  );
}
