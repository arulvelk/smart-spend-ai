// Browser-side client. Everything goes through the Next.js proxy at /api/*.
export type CategorySpend = { category: string; spend: number; txns: number };
export type Merchant = { merchant: string; spend: number; txns: number };
export type MonthPoint = { month: string; spend: number };
export type Budget = { category: string; monthly_limit: number; spend_month_to_date: number; pct_used: number };
export type Alert = { alert_id: string; alert_type: string; category: string; message: string; created_at: string };
export type Txn = {
  transaction_id: string;
  txn_date: string;
  raw_description: string;
  merchant_name: string | null;
  amount: number;
  direction: "debit" | "credit";
  category: string | null;
  category_source: string | null;
  category_confidence: number | null;
};
export type Accuracy = { evaluated: number; correct: number; accuracy_pct: number | null; avg_confidence: number | null };
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatReply = { answer: string; intent: { intent: string; category?: string | null; period?: string }; period?: { start: string; end: string }; data: Record<string, unknown> };
export type ReceiptResult = {
  receipt_id: string;
  parsed: {
    merchant_name: string;
    receipt_date: string | null;
    line_items: { description: string; quantity: number; amount: number }[];
    subtotal: number | null;
    tax: number | null;
    tip: number | null;
    total: number;
    category: string;
    confidence: number;
  };
  arithmetic_ok: boolean;
  matched_transaction: { transaction_id: string; txn_date: string; raw_description: string; amount: number } | null;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

const qs = (p: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]).toString();
  return s ? `?${s}` : "";
};

export const api = {
  categories: (month?: string) =>
    call<{ start: string; end: string; items: CategorySpend[]; top_merchants: Merchant[] }>(`analytics/categories${qs({ month })}`),
  monthly: () => call<{ items: MonthPoint[] }>("analytics/monthly"),
  budgets: () => call<{ items: Budget[] }>("budgets/status"),
  alerts: () => call<{ items: Alert[] }>("alerts"),
  accuracy: () => call<Accuracy>("categorize/accuracy"),
  transactions: (month?: string, category?: string) =>
    call<{ items: Txn[] }>(`transactions${qs({ month, category, limit: "300" })}`),
  categorize: () => call<{ pending: number; categorized: number }>("categorize", { method: "POST" }),
  chat: (message: string, history: ChatTurn[]) =>
    call<ChatReply>("chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, history }) }),
  receipt: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<ReceiptResult>("receipts", { method: "POST", body: form });
  },
};
