import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = { title: "FinAgent 1.0.0 · Research Workspace", description: "Deterministic historical quantitative research workspace" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body><AppShell>{children}</AppShell></body></html>; }
