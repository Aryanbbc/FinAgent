export function percent(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function number(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

export function currency(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits }).format(value);
}

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value));
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value));
}

export function label(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
