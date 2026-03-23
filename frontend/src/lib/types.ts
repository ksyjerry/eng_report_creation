export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
}

export interface JobDetail {
  job_id: string;
  status: JobStatus;
  progress: number;
  current_step: string;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface LogEntry {
  type: "log" | "progress" | "complete" | "error";
  level?: "info" | "warning" | "error" | "success";
  message?: string;
  step?: number;
  timestamp?: string;
  detail?: string;
  progress?: number;
  summary?: Record<string, unknown>;
}

export type AppStep = 1 | 2 | 3;

export interface ConversionState {
  step: AppStep;
  dsdFile: File | null;
  docxFile: File | null;
  jobId: string | null;
  logs: LogEntry[];
  progress: number;
  currentStep: string;
  result: Record<string, unknown> | null;
  error: string | null;
}
