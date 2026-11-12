export const ORG_ID = "meridian";
export const CURRENT_USER = "kavya.iyer";

export type QueueStatus = "all" | "needs_review" | "ready_for_approval" | "approved" | "rejected";

export type EvidenceMatch = {
  char_start: number;
  char_end: number;
  source_text: string;
};

export type FieldEvidence = {
  status: "found" | "ambiguous" | "not_found" | "unavailable";
  char_start: number | null;
  char_end: number | null;
  source_text: string | null;
  matches: EvidenceMatch[];
};

export type ReviewDetail = {
  code: string;
  title: string;
  description: string;
  evidence_fields: string[];
  direct_evidence: EvidenceMatch[];
  reference_matches: Array<{
    source: string;
    document_id: string | null;
    invoice_number: string | null;
    invoice_date: string | null;
    paid_on: string | null;
    total: string | null;
  }>;
};

export type InvoiceSummary = {
  id: number;
  document_id: string;
  supplier_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  currency: string | null;
  total: number | null;
  status: string;
  needs_review: number | boolean;
  review_reasons: string[];
  priority: string;
};

export type LineItem = {
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number;
};

export type Invoice = InvoiceSummary & {
  document_type: string;
  filename: string | null;
  raw_text: string;
  supplier_gstin: string | null;
  subtotal: number | null;
  cgst: number | null;
  sgst: number | null;
  igst: number | null;
  round_off: number | null;
  bank_account: string | null;
  ifsc: string | null;
  po_number: string | null;
  notes: string | null;
  line_items: LineItem[];
  warnings: string[];
  review_reasons: string[];
  review_details: ReviewDetail[];
  evidence: Record<string, FieldEvidence>;
  required_approvals: number;
  approval_count: number;
};

export type DecisionResult = {
  id: number;
  status: string;
  approvals?: number;
  required_approvals?: number;
  rejected_by?: string | null;
};

const orgHeaders = { "X-Org-Id": ORG_ID };

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed (HTTP ${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the HTTP status as the surfaced error when the response isn't JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function listInvoices(
  status: QueueStatus = "needs_review",
  limit = 300,
  offset = 0,
): Promise<InvoiceSummary[]> {
  const query = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  return readJson(await fetch(`/api/invoices?${query}`, { headers: orgHeaders }));
}

export async function getInvoice(id: number): Promise<Invoice> {
  return readJson(await fetch(`/api/invoices/${id}`, { headers: orgHeaders }));
}

export async function uploadInvoice(file: File): Promise<Invoice> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/invoices", { method: "POST", headers: orgHeaders, body });
  return readJson<Invoice>(response);
}

async function decide(id: number, action: "approve" | "reject", note: string): Promise<DecisionResult> {
  const response = await fetch(`/api/invoices/${id}/${action}`, {
    method: "POST",
    headers: { ...orgHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: CURRENT_USER, note }),
  });
  return readJson<DecisionResult>(response);
}

export const approveInvoice = (id: number, note: string) => decide(id, "approve", note);
export const rejectInvoice = (id: number, note: string) => decide(id, "reject", note);
