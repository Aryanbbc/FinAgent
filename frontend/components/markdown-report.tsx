import Markdown from "react-markdown";

const slug = (children: unknown) => String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

export function MarkdownReport({ markdown }: { markdown: string }) { return <article className="report-markdown"><Markdown skipHtml components={{ h2: ({ children }) => <h2 id={slug(children)}>{children}</h2>, h3: ({ children }) => <h3 id={slug(children)}>{children}</h3> }}>{markdown}</Markdown></article>; }
