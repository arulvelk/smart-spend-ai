"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { CATEGORIES, money, monthLabel, recentMonths } from "@/lib/format";
import { useLoad } from "./useLoad";

function Source({ source, confidence }: { source: string | null; confidence: number | null }) {
  if (!source) return <span className="src">pending</span>;
  if (source === "gemini") return <span className="src">Gemini {confidence != null ? `${Math.round(confidence * 100)}%` : ""}</span>;
  if (source === "receipt") return <span className="src">from receipt</span>;
  return <span className="src">seed</span>;
}

export default function Transactions() {
  const months = recentMonths(12);
  const [month, setMonth] = useState(months[0]);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const txns = useLoad(() => api.transactions(month, category || undefined), [month, category]);
  const pending = txns.data?.items.filter((t) => !t.category).length ?? 0;

  async function categorize() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.categorize();
      setNote(`Gemini categorized ${r.categorized} of ${r.pending} pending transactions.`);
      txns.reload();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="toolbar">
        <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
          {months.map((m) => <option key={m} value={m}>{monthLabel(m, "long")}</option>)}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <span className="spacer" />
        {note && <span className="muted" style={{ fontSize: 13 }}>{note}</span>}
        <button className="btn primary" onClick={categorize} disabled={busy}>
          {busy ? "Categorizing…" : `Categorize pending with Gemini${pending ? ` (${pending})` : ""}`}
        </button>
      </div>
      {txns.error && <p className="error">{txns.error}</p>}
      {txns.loading && <div className="skeleton" />}
      {txns.data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Date</th><th>Bank description → merchant</th><th>Category</th><th className="r">Amount</th></tr>
            </thead>
            <tbody>
              {txns.data.items.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>{t.txn_date}</td>
                  <td>
                    <div>{t.merchant_name ?? <span className="muted">—</span>}</div>
                    <div className="raw">{t.raw_description}</div>
                  </td>
                  <td>
                    {t.category ? <span className="chip">{t.category}</span> : <span className="muted">Uncategorized</span>}
                    <Source source={t.category_source} confidence={t.category_confidence} />
                  </td>
                  <td className={`r num ${t.direction === "credit" ? "credit" : ""}`}>
                    {t.direction === "credit" ? "+" : ""}{money(t.amount)}
                  </td>
                </tr>
              ))}
              {txns.data.items.length === 0 && <tr><td colSpan={4} className="muted">No transactions.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
