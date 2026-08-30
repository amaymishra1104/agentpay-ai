import type { Metadata } from "next";
import "./globals.css";
import { CustomerProvider } from "../lib/customer";
import { Navbar } from "../components/ui/Navbar";

export const metadata: Metadata = {
  title: "AgentPay — AI-Powered Agentic Commerce Platform",
  description:
    "Autonomous commerce agent with natural-language discovery, persistent shopping state, cryptographic Razorpay verification, and strict customer isolation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-[#f7f8fa] text-slate-900 selection:bg-slate-900 selection:text-white min-h-screen flex flex-col">
        <CustomerProvider>
          <Navbar />
          <div className="flex-1">{children}</div>
        </CustomerProvider>
      </body>
    </html>
  );
}
