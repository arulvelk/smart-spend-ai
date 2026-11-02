"use client";

import { useState } from "react";
import { api, type Txn } from "@/lib/api";
import { CATEGORIES, money, monthLabel, recentMonths } from "@/lib/format";
import { useLoad } from "./useLoad";

function Source({ source, confidence }: { source: string | null; confidence: number | null }) {
  if (!source) return <span className="src">pending</span>;
  if (source === "gemini") return <span className="src">Gemini {confidence != null ? `${Math.round(confidence * 100)}%` : ""}</span>;
  if (source === "receipt") return <span className="src">from receipt</span>;
  if (source === "user") return <span className="src">set by you</span>;
  return <span className="src">seed</span>;
}

export default function Transactions() {
  const months = recentMonths(12);
  const [month, setMonth] = useState(months[0]);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [account, setAccount] = useState("");
  const accounts = useLoad(() => api.accounts(), []);
  const txns = useLoad(() => api.transactions(month, category || undefined, account || undefined), [month, category, account]);
  const names = Object.fromEntries((accounts.data?.items ?? []).map((a) => [a.account_id, a.name]));

  async function recategorize(t: Txn, c: string) {
    try {
      await api.setCategory(t.transaction_id, c);
      txns.reload();
    } catch (e) {
      setNote((e as Error).message);
    }
  }
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
        <select value={account} onChange={(e) => setAccount(e.target.value)} aria-label="Account">
          <option value="">All accounts</option>
          {(accounts.data?.items ?? []).map((a) => <option key={a.account_id} value={a.account_id}>{a.name}</option>)}
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
                    <div className="raw">{t.raw_description}{t.account_id && names[t.account_id] ? ` · ${names[t.account_id]}` : ""}</div>
                  </td>
                  <td>
                    <select className="cat-select" value={t.category ?? ""} aria-label={`Category for ${t.raw_description}`}
                      onChange={(e) => e.target.value && recategorize(t, e.target.value)}>
                      {!t.category && <option value="">Uncategorized</option>}
                      {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                    </select>
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
