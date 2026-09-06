import Link from "next/link";

export default function NotFound() { return <section className="state"><p className="eyebrow">Not found</p><h2>This local research artifact is unavailable.</h2><p>It may have been removed, never created, or belong to a different SQLite database.</p><Link className="button-link" href="/experiments">Browse experiments</Link></section>; }
