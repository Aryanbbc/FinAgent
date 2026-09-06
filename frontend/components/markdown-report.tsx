import Markdown from "react-markdown";

export function MarkdownReport({ markdown }: { markdown: string }) { return <article className="report-markdown"><Markdown>{markdown}</Markdown></article>; }
