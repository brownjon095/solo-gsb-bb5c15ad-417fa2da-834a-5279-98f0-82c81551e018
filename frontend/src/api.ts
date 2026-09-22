import type { Defaults, DiagnoseResponse, ValidateResponse } from "./types";

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`请求失败 ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export function fetchDefaults(): Promise<Defaults> {
  return fetch("/api/defaults").then((r) => {
    if (!r.ok) throw new Error(`加载示例失败 ${r.status}`);
    return r.json() as Promise<Defaults>;
  });
}

export function diagnose(
  text: string,
  manifest: unknown,
  priority: string[],
): Promise<DiagnoseResponse> {
  return post<DiagnoseResponse>("/api/diagnose", { text, manifest, priority });
}

export function validateManifest(manifest: unknown): Promise<ValidateResponse> {
  return post<ValidateResponse>("/api/manifest/validate", { manifest });
}
