"use client";

import { useState } from "react";
import Overview from "@/components/Overview";
import Transactions from "@/components/Transactions";
import Receipts from "@/components/Receipts";
import Advisor from "@/components/Advisor";
import AddData from "@/components/AddData";

const TABS = ["Overview", "Transactions", "Add data", "Receipts", "Advisor"] as const;
type Tab = (typeof TABS)[number];

export default function Home() {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <main className="shell">
      <header className="top">
        <div className="brand">
          <h1>SmartSpend AI</h1>
          <span>Gemini on Vertex AI · BigQuery · Cloud Run</span>
        </div>
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
      </header>
      {tab === "Overview" && <Overview />}
      {tab === "Transactions" && <Transactions />}
      {tab === "Add data" && <AddData />}
      {tab === "Receipts" && <Receipts />}
      {tab === "Advisor" && <Advisor />}
      <footer>All data is synthetic. Built to demonstrate a serverless AI architecture on Google Cloud.</footer>
    </main>
  );
}
