// One fetch helper. In the demo the acting-as choice travels as a header; behind a real proxy it is ignored.
let actingAs: string | null = (() => {
  try { return localStorage.getItem("acting-as"); } catch { return null; }
})();

export function setActingAs(id: number) {
  actingAs = String(id);
  try { localStorage.setItem("acting-as", actingAs); } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", ...(actingAs ? { "X-Acting-As": actingAs } : {}) },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : data?.error || "That did not go through.";
    throw new ApiError(res.status, msg);
  }
  return data as T;
}
