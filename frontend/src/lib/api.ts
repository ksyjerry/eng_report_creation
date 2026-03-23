import type { JobResponse, LogEntry } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function uploadAndStart(
  dsdFile: File,
  docxFile: File
): Promise<JobResponse> {
  const formData = new FormData();
  formData.append("dsd_file", dsdFile);
  formData.append("docx_file", docxFile);

  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.detail || err.error || "Upload failed");
  }

  return res.json();
}

export function subscribeToProgress(
  jobId: string,
  onEvent: (event: LogEntry) => void,
  onError?: (error: Event) => void
): EventSource {
  const source = new EventSource(`${API_BASE}/api/jobs/${jobId}/stream`);

  source.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as LogEntry;
      onEvent(data);
    } catch {
      // ignore parse errors
    }
  };

  source.onerror = (e) => {
    onError?.(e);
  };

  return source;
}

export async function downloadResult(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}/download`);
  if (!res.ok) {
    throw new Error("Download failed");
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `SARA_result.docx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
}
