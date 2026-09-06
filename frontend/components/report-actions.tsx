"use client";

import { useState } from "react";

export function ReportActions({ markdown, downloadUrl }: { markdown: string; downloadUrl: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() { await navigator.clipboard.writeText(markdown); setCopied(true); window.setTimeout(() => setCopied(false), 1800); }
  return <div className="report-actions"><button type="button" onClick={copy}>{copied ? "Copied" : "Copy Markdown"}</button><a className="button-link" href={downloadUrl}>Download Markdown</a></div>;
}
