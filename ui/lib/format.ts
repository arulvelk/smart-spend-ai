const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const money = (n: number | null | undefined) => (n == null ? "–" : usd.format(n));
export const money0 = (n: number | null | undefined) => (n == null ? "–" : usd0.format(n));

export function monthLabel(iso: string, style: "short" | "long" = "short") {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", { month: style, year: style === "long" ? "numeric" : "2-digit", timeZone: "UTC" });
}

export function recentMonths(n: number, today = new Date()): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - i, 1));
    out.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

export const CATEGORIES = [
  "Groceries", "Dining", "Coffee", "Transportation", "Shopping", "Subscriptions", "Utilities", "Housing",
  "Healthcare", "Insurance", "Travel", "Entertainment", "Personal Care", "Fitness", "Fees", "Transfer", "Income",
];
