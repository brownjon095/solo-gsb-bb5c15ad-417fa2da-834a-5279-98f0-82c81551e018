import type { DiagnoseResponse, ValidationResponse } from "./types";

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = data?.detail;
    if (detail && typeof detail === "object" && detail.message) {
      throw new Error(detail.message);
    }
    if (typeof detail === "string") throw new Error(detail);
    throw new Error(`请求失败（HTTP ${res.status}）`);
  }
  return res.json();
}

export async function fetchSampleManifest(): Promise<string> {
  const res = await fetch("/api/sample-manifest");
  if (!res.ok) throw new Error("无法加载样例清单");
  return JSON.stringify(await res.json(), null, 2);
}

export function validateManifest(manifestText: string): Promise<ValidationResponse> {
  return postJson("/api/validate-manifest", { manifestText });
}

export function diagnoseText(
  text: string,
  manifestText: string,
  mode: "cluster" | "codepoint",
): Promise<DiagnoseResponse> {
  return postJson("/api/diagnose", { text, manifestText, mode });
}
