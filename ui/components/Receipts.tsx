"use client";

import { useState } from "react";
import { api, type ReceiptResult } from "@/lib/api";
import { money } from "@/lib/format";

export default function Receipts() {
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<ReceiptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);

  async function upload(file: File | undefined) {
    if (!file) return;
    setError(null);
    setResult(null);
    setPreview(URL.createObjectURL(file));
    setBusy(true);
    try {
      setResult(await api.receipt(file));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const p = result?.parsed;
  return (
    <div className="card">
      <h2>Scan a receipt</h2>
      <label
        className={`drop ${over ? "over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files[0]); }}
        style={{ display: "block" }}
      >
        <input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => upload(e.target.files?.[0])} />
        {busy ? "Gemini is reading the receipt…" : "Drop a receipt photo here, or click to choose one."}
        <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
          Sample receipts are in <code>data/out/receipts/</code> after running <code>data/generate.py</code>.
        </div>
      </label>
      {error && <p className="error">{error}</p>}
      {(preview || p) && (
        <div className="receipt-grid">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {preview && <img src={preview} alt="Uploaded receipt" />}
          {p && result && (
            <div>
              <h2 style={{ marginBottom: 4 }}>{p.merchant_name}</h2>
              <div className="muted" style={{ marginBottom: 10 }}>
                {p.receipt_date ?? "date unreadable"} · <span className="chip">{p.category}</span> · confidence {Math.round(p.confidence * 100)}%
              </div>
              <table>
                <tbody>
                  {p.line_items.map((li, i) => (
                    <tr key={i}><td>{li.quantity > 1 ? `${li.quantity} × ` : ""}{li.description}</td><td className="r num">{money(li.amount)}</td></tr>
                  ))}
                  <tr><td className="muted">Subtotal</td><td className="r num">{money(p.subtotal)}</td></tr>
                  <tr><td className="muted">Tax</td><td className="r num">{money(p.tax)}</td></tr>
                  {!!p.tip && <tr><td className="muted">Tip</td><td className="r num">{money(p.tip)}</td></tr>}
                  <tr><td><b>Total</b></td><td className="r num"><b>{money(p.total)}</b></td></tr>
                </tbody>
              </table>
              <p style={{ fontSize: 14 }}>
                {result.arithmetic_ok
                  ? <span><span style={{ color: "var(--good)" }}>✓</span> Line items, tax and tip add up to the total.</span>
                  : <span><span style={{ color: "var(--warning)" }}>●</span> The numbers don&apos;t add up. Please review this receipt.</span>}
              </p>
              <p style={{ fontSize: 14 }}>
                {result.matched_transaction
                  ? <>Matched to card transaction <span className="raw">{result.matched_transaction.raw_description}</span> on {result.matched_transaction.txn_date}; its category is now {p.category}.</>
                  : <span className="muted">No card transaction with this total within 3 days of the receipt date.</span>}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
