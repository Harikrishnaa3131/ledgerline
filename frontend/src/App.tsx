import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  approveInvoice,
  getInvoice,
  listInvoices,
  rejectInvoice,
  uploadInvoice,
  type EvidenceMatch,
  type FieldEvidence,
  type Invoice,
  type InvoiceSummary,
  type QueueStatus,
} from "./api";

const PAGE_SIZE = 300;
const FIELD_LABELS: Record<string, string> = {
  document_type: "Document type",
  supplier_name: "Supplier",
  supplier_gstin: "Supplier GSTIN",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  currency: "Currency",
  subtotal: "Subtotal",
  cgst: "CGST",
  sgst: "SGST",
  igst: "IGST",
  round_off: "Round-off",
  total: "Total",
  bank_account: "Bank account",
  ifsc: "IFSC",
  po_number: "PO number",
  notes: "Notes",
  buyer_gstin: "Buyer GSTIN",
};

function money(value: number | null | undefined, currency: string | null) {
  if (value === null || value === undefined) return "–";
  const symbol = currency === "USD" ? "$" : currency === "INR" ? "₹" : `${currency ?? ""} `;
  return symbol + value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function label(status: string) {
  return status.replace(/_/g, " ");
}

function evidenceStatusText(status: FieldEvidence["status"] | undefined) {
  if (status === "found") return "Source located";
  if (status === "ambiguous") return "Multiple exact matches";
  if (status === "not_found") return "Source not located";
  return "No source value";
}

function codePointOffsets(text: string) {
  const offsets = [0];
  let utf16Offset = 0;
  for (const character of text) {
    utf16Offset += character.length;
    offsets.push(utf16Offset);
  }
  return offsets;
}

function HighlightedDocument({
  text,
  matches,
  documentRef,
  firstMarkRef,
}: {
  text: string;
  matches: EvidenceMatch[];
  documentRef: (element: HTMLPreElement | null) => void;
  firstMarkRef: (element: HTMLElement | null) => void;
}) {
  const offsets = codePointOffsets(text);
  const spans = matches
    .map((match) => ({
      start: offsets[match.char_start] ?? text.length,
      end: offsets[match.char_end] ?? text.length,
    }))
    .filter((match) => match.end > match.start)
    .sort((a, b) => a.start - b.start);
  const pieces: React.ReactNode[] = [];
  let cursor = 0;
  spans.forEach((span, index) => {
    if (span.start < cursor) return;
    pieces.push(text.slice(cursor, span.start));
    pieces.push(
      <mark key={`${span.start}-${span.end}`} ref={index === 0 ? firstMarkRef : undefined}>
        {text.slice(span.start, span.end)}
      </mark>,
    );
    cursor = span.end;
  });
  pieces.push(text.slice(cursor));
  return (
    <pre className="document" ref={documentRef} tabIndex={0} aria-label="Original invoice text">
      {pieces}
    </pre>
  );
}

export default function App() {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus>("needs_review");
  const [filter, setFilter] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [activeEvidence, setActiveEvidence] = useState<{
    key: string;
    label: string;
    status: FieldEvidence["status"] | "direct";
    matches: EvidenceMatch[];
  } | null>(null);
  const decisionLock = useRef(false);
  const documentRef = useRef<HTMLPreElement | null>(null);
  const firstMarkRef = useRef<HTMLElement | null>(null);

  async function refreshQueue(status: QueueStatus = queueStatus) {
    const page = await listInvoices(status, PAGE_SIZE);
    setInvoices(page);
    setHasMore(page.length === PAGE_SIZE);
  }

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const page = await listInvoices(queueStatus, PAGE_SIZE);
        if (active) {
          setInvoices(page);
          setHasMore(page.length === PAGE_SIZE);
        }
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : String(error));
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [queueStatus]);

  useEffect(() => {
    firstMarkRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeEvidence]);

  async function open(id: number) {
    try {
      const invoice = await getInvoice(id);
      setSelected(invoice);
      setActiveEvidence(null);
      setNote("");
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function chooseField(key: string) {
    const evidence = selected?.evidence[key];
    setActiveEvidence({
      key,
      label: FIELD_LABELS[key] ?? key.replace(/^line_items\.\d+\./, "Line item · ").replace(/_/g, " "),
      status: evidence?.status ?? "unavailable",
      matches: evidence?.matches ?? [],
    });
  }

  function chooseDirectEvidence(key: string, labelText: string, matches: EvidenceMatch[]) {
    setActiveEvidence({ key, label: labelText, status: "direct", matches });
  }

  async function loadMore() {
    try {
      const next = await listInvoices(queueStatus, PAGE_SIZE, invoices.length);
      setInvoices((current) => [...current, ...next]);
      setHasMore(next.length === PAGE_SIZE);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setMessage(`Processing ${file.name}…`);
    try {
      const invoice = await uploadInvoice(file);
      setSelected(invoice);
      setActiveEvidence(null);
      setQueueStatus("all");
      setMessage(`Processed ${file.name}`);
      await refreshQueue("all");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
    event.target.value = "";
  }

  async function decide(action: "approve" | "reject") {
    if (!selected || decisionLock.current) return;
    decisionLock.current = true;
    setBusy(true);
    try {
      const result =
        action === "approve"
          ? await approveInvoice(selected.id, note)
          : await rejectInvoice(selected.id, note);
      setMessage(
        action === "approve"
          ? `Approval recorded (${result.approvals ?? 0} of ${result.required_approvals ?? selected.required_approvals})`
          : "Document rejected and recorded in the audit log",
      );
      setSelected(await getInvoice(selected.id));
      await refreshQueue();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      decisionLock.current = false;
      setBusy(false);
    }
  }

  const visibleInvoices = invoices.filter((invoice) => {
    const query = filter.trim().toLowerCase();
    return (
      !query ||
      [invoice.document_id, invoice.supplier_name, invoice.invoice_number]
        .some((value) => value?.toLowerCase().includes(query))
    );
  });
  const terminal = selected?.status === "approved" || selected?.status === "rejected";
  const cannotApprove = Boolean(
    selected?.review_reasons.includes("duplicate") ||
      selected?.review_reasons.includes("processing_error") ||
      selected?.document_type === "credit_note",
  );

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Ledgerline</h1>
          <span className="org">Meridian Precision Components · AP review</span>
        </div>
        <label className="upload">
          Upload document
          <input type="file" accept=".txt,.eml,.json" onChange={onUpload} />
        </label>
      </header>
      {message && (
        <p className="message" role="status">
          {message}
        </p>
      )}

      <main className="workspace">
        <aside className="queue" aria-label="Reviewer queue">
          <div className="queue-heading">
            <div>
              <h2>Review queue</h2>
              <p>{visibleInvoices.length} documents shown · highest risk first</p>
            </div>
            <select
              aria-label="Queue status"
              value={queueStatus}
              onChange={(event) => setQueueStatus(event.target.value as QueueStatus)}
            >
              <option value="needs_review">Needs review</option>
              <option value="ready_for_approval">Ready for approval</option>
              <option value="all">All documents</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <input
            className="queue-search"
            type="search"
            placeholder="Search supplier, invoice, or ID"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            aria-label="Search review queue"
          />
          <div className="queue-list">
            {visibleInvoices.map((invoice) => (
              <button
                type="button"
                key={invoice.id}
                className={`queue-item ${selected?.id === invoice.id ? "active" : ""}`}
                onClick={() => void open(invoice.id)}
              >
                <span className={`priority ${invoice.priority.toLowerCase()}`}>{invoice.priority}</span>
                <strong>{invoice.supplier_name ?? "Unknown supplier"}</strong>
                <span>{invoice.invoice_number ?? invoice.document_id}</span>
                <span className="queue-meta">
                  {money(invoice.total, invoice.currency)} · {label(invoice.status)}
                </span>
                {invoice.review_reasons.length > 0 && (
                  <span className="reason-preview">{invoice.review_reasons.map((reason) => reason.replace(/_/g, " ")).join(" · ")}</span>
                )}
              </button>
            ))}
            {visibleInvoices.length === 0 && <p className="empty">No documents in this queue.</p>}
            {hasMore && (
              <button type="button" className="load-more" onClick={() => void loadMore()}>
                Load next {PAGE_SIZE}
              </button>
            )}
          </div>
        </aside>

        <section className="review" aria-label="Selected invoice review">
          {!selected ? (
            <p className="empty review-empty">Choose a document from the prioritized queue.</p>
          ) : (
            <>
              <div className="review-title">
                <div>
                  <span className={`badge ${selected.status}`}>{label(selected.status)}</span>
                  <h2>{selected.supplier_name ?? "Unknown supplier"}</h2>
                  <p>{selected.document_id} · {selected.invoice_number ?? "No invoice number"}</p>
                </div>
                <div className="approval-progress">
                  Approvals {selected.approval_count} / {selected.required_approvals}
                </div>
              </div>

              {selected.review_details.length > 0 && (
                <section className="reason-list" aria-label="Review reasons">
                  <h3>Why this needs attention</h3>
                  {selected.review_details.map((reason) => (
                    <article className="reason-card" key={reason.code}>
                      <div>
                        <strong>{reason.title}</strong>
                        <p>{reason.description}</p>
                      </div>
                      <div className="reason-evidence">
                        {reason.evidence_fields.map((key) => (
                          <button type="button" key={key} onClick={() => chooseField(key)}>
                            {FIELD_LABELS[key] ?? key.replace(/^line_items\.\d+\./, "Line item · ").replace(/_/g, " ")}
                          </button>
                        ))}
                        {reason.reference_matches.map((match, index) => (
                          <span className="reference-match" key={`${match.source}-${index}`}>
                            <strong>{match.source}</strong>
                            <span>
                              {match.document_id ? `${match.document_id} · ` : ""}
                              {match.invoice_number ?? "No invoice number"}
                              {match.invoice_date ? ` · ${match.invoice_date}` : ""}
                              {match.paid_on ? ` · paid ${match.paid_on}` : ""}
                              {match.total ? ` · ${match.total}` : ""}
                            </span>
                          </span>
                        ))}
                        {reason.direct_evidence.length > 0 && (
                          <button
                            type="button"
                            onClick={() => chooseDirectEvidence(reason.code, reason.title, reason.direct_evidence)}
                          >
                            Show triggering text
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
                </section>
              )}

              <div className="review-columns">
                <section className="invoice-fields" aria-label="Extracted invoice fields">
                  <h3>Extracted values</h3>
                  <div className="field-list">
                    {[
                      ["supplier_name", selected.supplier_name],
                      ["supplier_gstin", selected.supplier_gstin],
                      ["invoice_number", selected.invoice_number],
                      ["invoice_date", selected.invoice_date],
                      ["currency", selected.currency],
                      ["po_number", selected.po_number],
                      ["subtotal", money(selected.subtotal, selected.currency)],
                      ["cgst", money(selected.cgst, selected.currency)],
                      ["sgst", money(selected.sgst, selected.currency)],
                      ["igst", money(selected.igst, selected.currency)],
                      ["round_off", money(selected.round_off, selected.currency)],
                      ["total", money(selected.total, selected.currency)],
                      ["bank_account", selected.bank_account],
                      ["ifsc", selected.ifsc],
                    ].map(([key, value]) => {
                      const fieldKey = String(key);
                      const source = selected.evidence[fieldKey];
                      return (
                        <div className="field-row" key={fieldKey}>
                          <span>{FIELD_LABELS[fieldKey]}</span>
                          <button
                            type="button"
                            className={activeEvidence?.key === fieldKey ? "selected-field" : ""}
                            onClick={() => chooseField(fieldKey)}
                          >
                            {value === null || value === undefined || value === "" ? "–" : value}
                          </button>
                          <small>{evidenceStatusText(source?.status)}</small>
                        </div>
                      );
                    })}
                  </div>

                  <h3>Line items</h3>
                  <div className="line-items">
                    {selected.line_items.map((item, index) => (
                      <div className="line-item" key={`${index}-${item.description}`}>
                        <EvidenceValue fieldKey={`line_items.${index}.description`} value={item.description} onSelect={chooseField} />
                        <div className="line-numbers">
                          <EvidenceValue fieldKey={`line_items.${index}.quantity`} value={`Qty ${item.quantity ?? "–"}`} onSelect={chooseField} />
                          <EvidenceValue fieldKey={`line_items.${index}.unit_price`} value={`Rate ${money(item.unit_price, selected.currency)}`} onSelect={chooseField} />
                          <EvidenceValue fieldKey={`line_items.${index}.amount`} value={`Amount ${money(item.amount, selected.currency)}`} onSelect={chooseField} />
                        </div>
                      </div>
                    ))}
                  </div>
                  {activeEvidence && (
                    <p className={`evidence-status ${activeEvidence.status}`}>
                      {activeEvidence.status === "direct"
                        ? "Exact text behind the review reason."
                        : evidenceStatusText(activeEvidence.status)}
                      {activeEvidence.status === "ambiguous" && " All exact occurrences are highlighted."}
                      {activeEvidence.status === "not_found" && " The source value could not be located reliably."}
                    </p>
                  )}
                  {selected.warnings.length > 0 && (
                    <details className="warnings">
                      <summary>Processing notes</summary>
                      <ul>{selected.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
                    </details>
                  )}
                </section>

                <section className="source-panel" aria-label="Original source document">
                  <div className="source-heading">
                    <div>
                      <h3>Original document</h3>
                      <p>{selected.filename ?? selected.document_id}</p>
                    </div>
                    {activeEvidence && <span>{activeEvidence.label}</span>}
                  </div>
                  <HighlightedDocument
                    text={selected.raw_text}
                    matches={activeEvidence?.matches ?? []}
                    documentRef={(element) => { documentRef.current = element; }}
                    firstMarkRef={(element) => { firstMarkRef.current = element; }}
                  />
                </section>
              </div>

              <section className="decision" aria-label="Decision controls">
                <label htmlFor="decision-note">Reviewer note</label>
                <textarea
                  id="decision-note"
                  placeholder={selected.needs_review ? "Required when approving a reviewed invoice" : "Optional audit note"}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  disabled={Boolean(terminal) || busy}
                />
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => void decide("approve")}
                    disabled={Boolean(terminal) || busy || cannotApprove || (Boolean(selected.needs_review) && !note.trim())}
                  >
                    {busy ? "Saving…" : "Approve"}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void decide("reject")}
                    disabled={Boolean(terminal) || busy}
                  >
                    Reject
                  </button>
                </div>
                {cannotApprove && <p className="hint">Duplicates, credit notes and processing failures cannot be approved.</p>}
              </section>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

function EvidenceValue({
  fieldKey,
  value,
  onSelect,
}: {
  fieldKey: string;
  value: string;
  onSelect: (key: string) => void;
}) {
  return (
    <button type="button" className="evidence-value" onClick={() => onSelect(fieldKey)}>
      {value}
    </button>
  );
}
