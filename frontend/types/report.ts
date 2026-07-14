export interface Finding {
  requirement_key: string;
  citation: string;
  source_url: string | null;
  jurisdiction: string;
  status: "compliant" | "contradicts" | "needs_review" | "absent";
  explanation: string;
  summary: string | null;
  verifier_confirmed: boolean | null;
  verifier_flag: string | null;
}

export interface FamilyGroup {
  family_key: string;
  friendly_title: string | null;
  findings: Finding[];
}

export interface AwarenessItem {
  citation: string;
  summary: string;
  source_url: string | null;
  jurisdiction: string;
}

export interface ProcessingWarnings {
  needs_reparse: string[];
  never_parsed: string[];
  compliance_judgment_failed: string[];
}

export interface Report {
  lease_id: string;
  generated_at: string;
  summary: {
    total: number;
    compliant: number;
    contradicts: number;
    needs_review: number;
    absent: number;
    disputed_by_verifier: number;
  };
  requirement_findings: FamilyGroup[];
  awareness_items: AwarenessItem[];
  processing_warnings: ProcessingWarnings;
  disclaimer: string;
}

export interface LeaseStatusResponse {
  lease_id: string;
  status: string;
  error_message?: string;
  report?: Report;
}
