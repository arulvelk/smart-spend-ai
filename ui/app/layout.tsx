import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartSpend AI",
  description: "Personal budgeting and advice on Google Cloud: Gemini on Vertex AI, BigQuery, Cloud Run.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
