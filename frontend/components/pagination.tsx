import Link from "next/link";
import { Pagination as PaginationMeta } from "@/lib/api";

export function Pagination({ pagination, pathname, query }: { pagination: PaginationMeta; pathname: string; query: Record<string, string | undefined> }) {
  if (pagination.total <= pagination.limit) return <p className="table-meta">{pagination.total} result{pagination.total === 1 ? "" : "s"}</p>;
  const url = (offset: number) => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => { if (value) params.set(key, value); });
    params.set("limit", String(pagination.limit)); params.set("offset", String(Math.max(0, offset)));
    return `${pathname}?${params.toString()}`;
  };
  const start = pagination.offset + 1; const end = Math.min(pagination.offset + pagination.limit, pagination.total);
  return <nav className="pagination" aria-label="Pagination"><span>{start}–{end} of {pagination.total}</span>{pagination.offset > 0 ? <Link className="button-link" href={url(pagination.offset - pagination.limit)}>Previous</Link> : <span className="button-link disabled">Previous</span>}{pagination.offset + pagination.limit < pagination.total ? <Link className="button-link" href={url(pagination.offset + pagination.limit)}>Next</Link> : <span className="button-link disabled">Next</span>}</nav>;
}
