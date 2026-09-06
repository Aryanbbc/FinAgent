"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <section className="state error"><p className="eyebrow">Local workspace issue</p><h2>We could not load this research view.</h2><p>The API may be unavailable, the requested artifact may be missing, or local data needs attention. No simulation was changed.</p><button type="button" onClick={reset}>Try again</button></section>;
}
