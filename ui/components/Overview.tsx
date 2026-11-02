"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Budget } from "@/lib/api";
import { money, money0, monthLabel, recentMonths } from "@/lib/format";
import { useLoad } from "./useLoad";

function ChartTip({ active, payload, label, labelFmt }: { active?: boolean; payload?: { value: number; payload: Record<string, unknown> }[]; label?: string; labelFmt?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="tooltip">
      <b>{labelFmt ? labelFmt(String(label)) : label}</b>
      <span className="num">{money(p.value)}</span>
      {typeof p.payload.txns === "number" && <span className="muted"> · {p.payload.txns} transactions</span>}
    </div>
  );
}

function budgetStatus(b: Budget) {
  if (b.pct_used >= 100) return { color: "var(--critical)", label: "Over budget", icon: "▲" };
  if (b.pct_used >= 80) return { color: "var(--warning)", label: "Near limit", icon: "●" };
  return { color: "var(--good)", label: "On track", icon: "✓" };
}

export default function Overview() {
  const months = recentMonths(12);
  const [month, setMonth] = useState(months[0]);
  const cats = useLoad(() => api.categories(month), [month]);
  const prev = useLoad(() => api.categories(months[1]), []);
  const trend = useLoad(() => api.monthly(), []);
  const budgets = useLoad(() => api.budgets(), []);
  const alerts = useLoad(() => api.alerts(), []);
  const acc = useLoad(() => api.accuracy(), []);

  const thisMonthTotal = month === months[0] ? cats.data?.items.reduce((s, c) => s + c.spend, 0) : undefined;
  const lastMonthTotal = prev.data?.items.reduce((s, c) => s + c.spend, 0);
  const over = budgets.data?.items.filter((b) => b.pct_used >= 100).length;
  const catRows = (cats.data?.items ?? []).filter((c) => c.category !== "Housing").slice(0, 10);

  return (
    <div className="grid">
      <section className="grid kpis">
        <div className="card kpi">
          <div className="label">Spent this month</div>
          <div className="value num">{money0(thisMonthTotal ?? budgets.data?.items.reduce((s, b) => s + b.spend_month_to_date, 0))}</div>
          <div className="sub">excludes transfers and income</div>
        </div>
        <div className="card kpi">
          <div className="label">Last month</div>
          <div className="value num">{money0(lastMonthTotal)}</div>
          <div className="sub">{monthLabel(months[1], "long")}</div>
        </div>
        <div className="card kpi">
          <div className="label">Budgets over limit</div>
          <div className="value num">{over ?? "–"}<span className="muted" style={{ fontSize: 15 }}> / {budgets.data?.items.length ?? "–"}</span></div>
          <div className="sub">month to date</div>
        </div>
        <div className="card kpi">
          <div className="label">Gemini categorization accuracy</div>
          <div className="value num">{acc.data?.accuracy_pct != null ? `${acc.data.accuracy_pct}%` : "–"}</div>
          <div className="sub">{acc.data ? `${acc.data.correct} of ${acc.data.evaluated} vs. ground truth` : "run categorization first"}</div>
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <h2>Monthly spending, last 12 months</h2>
          {trend.error && <p className="error">{trend.error}</p>}
          {trend.loading ? <div className="skeleton" /> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={trend.data?.items ?? []} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="month" tickFormatter={(m) => monthLabel(m)} tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={{ stroke: "var(--axis)" }} tickLine={false} />
                <YAxis tickFormatter={(v) => `$${Math.round(v / 1000)}k`} tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} width={44} />
                <Tooltip cursor={{ fill: "var(--surface-2)" }} content={<ChartTip labelFmt={(l) => monthLabel(l, "long")} />} />
                <Bar dataKey="spend" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h2>
            Budgets this month
            <span className="muted" style={{ fontWeight: 400 }}>spent / limit</span>
          </h2>
          {budgets.error && <p className="error">{budgets.error}</p>}
          {budgets.data?.items.map((b) => {
            const s = budgetStatus(b);
            return (
              <div className="budget" key={b.category}>
                <span>{b.category}</span>
                <div className="bar" title={`${b.pct_used}% used`}>
                  <i style={{ width: `${Math.min(b.pct_used, 100)}%`, background: s.color }} />
                </div>
                <span className="status num">
                  <span style={{ color: s.color }} aria-hidden>{s.icon}</span>
                  {money0(b.spend_month_to_date)} / {money0(b.monthly_limit)}
                  <span className="muted">· {s.label}</span>
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <h2>
            Spending by category
            <select value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
              {months.map((m) => <option key={m} value={m}>{monthLabel(m, "long")}</option>)}
            </select>
          </h2>
          {cats.error && <p className="error">{cats.error}</p>}
          {cats.loading ? <div className="skeleton" /> : catRows.length === 0 ? <p className="muted">No spending recorded for this month yet.</p> : (
            <ResponsiveContainer width="100%" height={Math.max(160, catRows.length * 30)}>
              <BarChart data={catRows} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid horizontal={false} stroke="var(--grid)" />
                <XAxis type="number" tickFormatter={(v) => `$${v}`} tick={{ fill: "var(--muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="category" width={110} tick={{ fill: "var(--ink-2)", fontSize: 13 }} axisLine={{ stroke: "var(--axis)" }} tickLine={false} />
                <Tooltip cursor={{ fill: "var(--surface-2)" }} content={<ChartTip />} />
                <Bar dataKey="spend" fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          )}
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>Rent is left out of this chart so the smaller categories stay readable.</p>
        </div>

        <div className="card">
          <h2>Alerts from the daily job</h2>
          {alerts.error && <p className="error">{alerts.error}</p>}
          {alerts.data && alerts.data.items.length === 0 && <p className="muted">No alerts yet. The daily Cloud Function raises them when a budget is at risk.</p>}
          <ul className="alerts">
            {alerts.data?.items.map((a) => (
              <li key={a.alert_id}>
                <span aria-hidden style={{ color: a.alert_type === "budget_exceeded" ? "var(--critical)" : "var(--warning)" }}>
                  {a.alert_type === "budget_exceeded" ? "▲" : "●"}
                </span>
                <span>{a.message}</span>
              </li>
            ))}
          </ul>
          {cats.data && cats.data.top_merchants.length > 0 && (
            <>
              <h2 style={{ marginTop: 16 }}>Top merchants, {monthLabel(month, "long")}</h2>
              <table>
                <tbody>
                  {cats.data.top_merchants.map((m) => (
                    <tr key={m.merchant}><td>{m.merchant}</td><td className="r num">{money(m.spend)}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
