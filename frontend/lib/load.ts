export async function load<T>(promise: Promise<T>): Promise<{ data: T | null; error: string | null }> {
  try { return { data: await promise, error: null }; } catch (error) { return { data: null, error: error instanceof Error ? error.message : "Unable to load local research data." }; }
}
