"use client";

import { useMemo, useState } from "react";
import { api, type Account, type StatementPreview } from "@/lib/api";
import { CATEGORIES, money } from "@/lib/format";
import { useLoad } from "./useLoad";

const TYPES: Record<Account["type"], string> = {
  credit_card: "Credit card",
  checking: "Checking",
  savings: "Savings",
  cash: "Cash",
};

const today = () => new Date().toISOString().slice(0, 10);

export function accountLabel(a: Account) {
  return `${a.name}${a.last4 ? ` ··${a.last4}` : ""}${a.is_demo ? " (demo)" : ""}`;
}

function AccountSelect({ accounts, value, onChange }: { accounts: Account[]; value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Account" required>
      <option value="">Choose an account…</option>
      {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{accountLabel(a)}</option>)}
    </select>
  );
}

function Accounts({ accounts, reload }: { accounts: Account[]; reload: () => void }) {
  const [form, setForm] = useState({ name: "", type: "credit_card", institution: "", last4: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createAccount({ name: form.name, type: form.type, institution: form.institution || undefined, last4: form.last4 || undefined });
      setForm({ name: "", type: "credit_card", institution: "", last4: "" });
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Accounts and cards</h2>
      <table>
        <thead><tr><th>Name</th><th>Type</th><th>Institution</th><th className="r">Transactions</th></tr></thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.account_id}>
              <td>{a.name}{a.last4 && <span className="muted"> ··{a.last4}</span>}{a.is_demo && <span className="src">synthetic demo</span>}</td>
              <td>{TYPES[a.type] ?? a.type}</td>
              <td>{a.institution ?? <span className="muted">—</span>}</td>
              <td className="r num">{a.txns ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="form-row" onSubmit={submit} style={{ marginTop: 14 }}>
        <input type="text" placeholder="Name, e.g. Chase Sapphire" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={80} aria-label="Account name" />
        <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} aria-label="Account type">
          {Object.entries(TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <input type="text" placeholder="Bank (optional)" value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} maxLength={80} aria-label="Institution" />
        <input type="text" placeholder="Last 4" value={form.last4} onChange={(e) => setForm({ ...form, last4: e.target.value.replace(/\D/g, "").slice(0, 4) })} inputMode="numeric" pattern="\d{4}" style={{ width: 90 }} aria-label="Last 4 digits" />
        <button className="btn primary" disabled={busy}>{busy ? "Adding…" : "Add account"}</button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function ManualEntry({ accounts }: { accounts: Account[] }) {
  const blank = { account_id: "", txn_date: today(), description: "", amount: "", direction: "debit", category: "" };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const t = await api.addTransaction({
        account_id: form.account_id, txn_date: form.txn_date, description: form.description,
        amount: Number(form.amount), direction: form.direction, category: form.category || undefined,
      });
      const how = t.category_source === "gemini" ? `Gemini filed it under ${t.category}` : `filed under ${t.category}`;
      setNote(`Added ${money(Number(t.amount))} at ${t.merchant_name ?? t.raw_description}; ${how}.`);
      setForm({ ...blank, account_id: form.account_id, txn_date: form.txn_date });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Add a transaction</h2>
      <form className="form-grid" onSubmit={submit}>
        <label>Account<AccountSelect accounts={accounts} value={form.account_id} onChange={(v) => setForm({ ...form, account_id: v })} /></label>
        <label>Date<input type="date" value={form.txn_date} max={today()} onChange={(e) => setForm({ ...form, txn_date: e.target.value })} required /></label>
        <label className="wide">Description<input type="text" placeholder="e.g. Farmers market" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required maxLength={200} /></label>
        <label>Amount (USD)<input type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required /></label>
        <label>Type
          <select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
            <option value="debit">Money out</option>
            <option value="credit">Money in</option>
          </select>
        </label>
        <label>Category
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Let Gemini decide</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <div className="wide"><button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Add transaction"}</button></div>
      </form>
      {note && <p style={{ fontSize: 14 }}><span style={{ color: "var(--good)" }}>✓</span> {note}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function StatementUpload({ accounts }: { accounts: Account[] }) {
  const [accountId, setAccountId] = useState("");
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [keep, setKeep] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"" | "reading" | "importing">("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const imports = useLoad(() => api.imports(), []);

  async function read(file: File | undefined) {
    if (!file || !accountId) return;
    setBusy("reading");
    setError(null);
    setNote(null);
    setPreview(null);
    try {
      const p = await api.previewStatement(accountId, file);
      setPreview(p);
      setKeep(new Set(p.rows.filter((r) => !r.duplicate).map((r) => r.transaction_id)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function importRows() {
    if (!preview) return;
    setBusy("importing");
    setError(null);
    try {
      const rows = preview.rows.filter((r) => keep.has(r.transaction_id))
        .map(({ txn_date, description, amount, direction }) => ({ txn_date, description, amount, direction }));
      const r = await api.importStatement(preview, rows);
      setNote(`Imported ${r.inserted} transaction${r.inserted === 1 ? "" : "s"} and skipped ${r.skipped}. Gemini categorized the new ones.`);
      setPreview(null);
      imports.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function undo(id: string) {
    const r = await api.undoImport(id);
    setNote(`Removed ${r.deleted} transaction${r.deleted === 1 ? "" : "s"} from that import.`);
    imports.reload();
  }

  const totals = useMemo(() => {
    const rows = preview?.rows.filter((r) => keep.has(r.transaction_id)) ?? [];
    return {
      n: rows.length,
      out: rows.filter((r) => r.direction === "debit").reduce((s, r) => s + r.amount, 0),
      in: rows.filter((r) => r.direction === "credit").reduce((s, r) => s + r.amount, 0),
    };
  }, [preview, keep]);

  return (
    <div className="card">
      <h2>Upload a statement</h2>
      <p className="muted" style={{ fontSize: 13.5, marginTop: -4 }}>
        CSV exports are read with rules. PDFs and photos are read by Gemini. You review every row before anything is saved, and rows already in BigQuery are skipped.
      </p>
      <div className="form-row">
        <AccountSelect accounts={accounts} value={accountId} onChange={setAccountId} />
        <label className={`btn ${accountId ? "primary" : ""}`} aria-disabled={!accountId} style={{ cursor: accountId ? "pointer" : "not-allowed", opacity: accountId ? 1 : 0.55 }}>
          {busy === "reading" ? "Reading…" : "Choose CSV or PDF"}
          <input type="file" accept=".csv,.pdf,.png,.jpg,.jpeg" hidden disabled={!accountId || !!busy} onChange={(e) => { read(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
        {!accountId && <span className="muted" style={{ fontSize: 13 }}>Pick the account this statement belongs to first.</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {note && <p style={{ fontSize: 14 }}><span style={{ color: "var(--good)" }}>✓</span> {note}</p>}

      {preview && (
        <div style={{ marginTop: 14 }}>
          <div className="toolbar">
            <span style={{ fontSize: 14 }}>
              <b>{preview.filename}</b> · read by {preview.parser === "csv-rules" ? "CSV rules" : preview.parser} · {preview.rows.length} rows
            </span>
            <span className="spacer" />
            <span className="num muted" style={{ fontSize: 13 }}>{totals.n} selected · out {money(totals.out)} · in {money(totals.in)}</span>
            <button className="btn" onClick={() => setPreview(null)} disabled={!!busy}>Cancel</button>
            <button className="btn primary" onClick={importRows} disabled={!!busy || totals.n === 0}>
              {busy === "importing" ? "Importing…" : `Import ${totals.n}`}
            </button>
          </div>
          {preview.warnings.map((w) => <p key={w} style={{ fontSize: 13.5 }}><span style={{ color: "var(--warning)" }}>●</span> {w}</p>)}
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
            <table>
              <thead><tr><th></th><th>Date</th><th>Description</th><th className="r">Amount</th></tr></thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.transaction_id} style={{ opacity: r.duplicate ? 0.5 : 1 }}>
                    <td>
                      <input type="checkbox" checked={keep.has(r.transaction_id)} aria-label={`Import ${r.description}`}
                        onChange={(e) => { const k = new Set(keep); if (e.target.checked) k.add(r.transaction_id); else k.delete(r.transaction_id); setKeep(k); }} />
                    </td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>{r.txn_date}</td>
                    <td><span className="raw" style={{ fontSize: 12.5 }}>{r.description}</span>{r.duplicate && <span className="src">already imported</span>}</td>
                    <td className={`r num ${r.direction === "credit" ? "credit" : ""}`}>{r.direction === "credit" ? "+" : ""}{money(r.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {imports.data && imports.data.items.length > 0 && (
        <>
          <h2 style={{ marginTop: 20 }}>Recent imports</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>File</th><th>Account</th><th>Read by</th><th className="r">Added</th><th></th></tr></thead>
              <tbody>
                {imports.data.items.map((i) => (
                  <tr key={i.import_id}>
                    <td>{i.filename}<div className="muted" style={{ fontSize: 12 }}>{i.created_at.slice(0, 16).replace("T", " ")}</div></td>
                    <td>{i.account_name ?? "—"}</td>
                    <td>{i.parser === "csv-rules" ? "CSV rules" : i.parser}</td>
                    <td className="r num">{i.rows_inserted}{i.rows_skipped ? <span className="muted"> (+{i.rows_skipped} skipped)</span> : null}</td>
                    <td className="r">{i.status === "undone" ? <span className="muted">undone</span> : <button className="btn" onClick={() => undo(i.import_id)}>Undo</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function AddData() {
  const accounts = useLoad(() => api.accounts(), []);
  const list = accounts.data?.items ?? [];
  return (
    <div className="grid">
      {accounts.error && <p className="error">{accounts.error}</p>}
      <StatementUpload accounts={list} />
      <section className="grid two">
        <ManualEntry accounts={list} />
        <Accounts accounts={list} reload={accounts.reload} />
      </section>
    </div>
  );
}
