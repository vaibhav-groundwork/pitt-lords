"use client";

import { useEffect, useRef, useState } from "react";
import type { Report, LeaseStatusResponse } from "@/types/report";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface UseLeaseReportResult {
  status: string;   // "loading" before first response, then any backend status
  report: Report | null;
  errorMessage: string | null;
  notFound: boolean;
}

/**
 * Polls GET /leases/:leaseId every 2 s, stops when the lease reaches a
 * terminal state (complete / failed / 404).
 *
 * Initial status is the hook-internal sentinel "loading" so the UI has a
 * defined value before the first response arrives -- it is never sent by
 * the backend and must not be compared against real backend status strings.
 *
 * A single AbortController ref (not a separate isFetching flag) guarantees
 * only the latest request's response is acted upon. AbortErrors are silently
 * discarded; genuine network errors are silently ignored per tick so transient
 * failures keep retrying rather than surfacing as permanent failures.
 *
 * React Strict Mode mounts/unmounts/remounts every component once in dev.
 * The cleanup function clears the interval AND aborts the current controller
 * so double-invocation never leaves a dangling interval or a stale response
 * setting state after unmount.
 */
export function useLeaseReport(leaseId: string): UseLeaseReportResult {
  const [status, setStatus] = useState("loading");
  const [report, setReport] = useState<Report | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  // One ref for the current in-flight controller. Persists across re-renders
  // but is aborted and replaced at the start of every fetch tick.
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let stopped = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    function stop() {
      stopped = true;
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    }

    async function doFetch() {
      if (stopped) return;

      // Abort the previous in-flight request before starting a new one.
      if (controllerRef.current) {
        controllerRef.current.abort();
      }
      const controller = new AbortController();
      controllerRef.current = controller;

      try {
        const response = await fetch(`${API_URL}/leases/${leaseId}`, {
          signal: controller.signal,
        });

        // Guard: cleanup may have run while this await was resolving.
        if (stopped) return;

        if (response.status === 404) {
          setNotFound(true);
          stop();
          return;
        }

        const body: LeaseStatusResponse = await response.json();

        if (stopped) return;

        if (body.status === "complete") {
          setStatus("complete");
          setReport(body.report ?? null);
          stop();
        } else if (body.status === "failed") {
          setStatus("failed");
          setErrorMessage(body.error_message ?? "An unknown error occurred.");
          stop();
        } else {
          // Any in-progress status ("uploaded", "extracting_text", etc.) --
          // update the displayed stage and keep polling.
          setStatus(body.status);
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          // Intentional cancellation from abort() above -- not an error,
          // do not touch any state, do not log.
          return;
        }
        // Genuine network failure: silently ignore for this tick so polling
        // continues rather than surfacing a transient error as permanent.
      }
    }

    // Fire immediately so the UI updates without waiting 2 s for the first tick.
    doFetch();
    intervalId = setInterval(doFetch, 2000);

    return () => {
      // Must clear the interval AND abort the in-flight controller so that
      // React Strict Mode's deliberate remount doesn't leave a dangling
      // interval or a stale response setting state after cleanup.
      stop();
      if (controllerRef.current) {
        controllerRef.current.abort();
        controllerRef.current = null;
      }
    };
  }, [leaseId]);

  return { status, report, errorMessage, notFound };
}
