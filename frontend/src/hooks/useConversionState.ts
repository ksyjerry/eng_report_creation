"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AppStep, ConversionState, LogEntry } from "@/lib/types";
import { cancelJob, subscribeToProgress, uploadAndStart } from "@/lib/api";

const initialState: ConversionState = {
  step: 1,
  dsdFile: null,
  docxFile: null,
  jobId: null,
  logs: [],
  progress: 0,
  currentStep: "",
  result: null,
  error: null,
};

export function useConversionState() {
  const [state, setState] = useState<ConversionState>(initialState);
  const eventSourceRef = useRef<EventSource | null>(null);

  const setDsdFile = useCallback((file: File | null) => {
    setState((s) => ({ ...s, dsdFile: file }));
  }, []);

  const setDocxFile = useCallback((file: File | null) => {
    setState((s) => ({ ...s, docxFile: file }));
  }, []);

  const startProcessing = useCallback(async () => {
    if (!state.dsdFile || !state.docxFile) return;

    setState((s) => ({ ...s, step: 2, logs: [], progress: 0, error: null }));

    try {
      const job = await uploadAndStart(state.dsdFile, state.docxFile);
      setState((s) => ({ ...s, jobId: job.job_id }));

      // SSE 연결
      const source = subscribeToProgress(
        job.job_id,
        (event: LogEntry) => {
          setState((s) => {
            const newLogs = [...s.logs, event];

            if (event.type === "complete") {
              source.close();
              return {
                ...s,
                step: 3 as AppStep,
                logs: newLogs,
                progress: 100,
                result: event.summary || {},
              };
            }

            if (event.type === "error") {
              source.close();
              return {
                ...s,
                step: 3 as AppStep,
                logs: newLogs,
                error: event.message || "Unknown error",
              };
            }

            return {
              ...s,
              logs: newLogs,
              progress: event.progress ?? s.progress,
              currentStep: event.message || s.currentStep,
            };
          });
        },
        () => {
          // SSE error — 연결 닫고 에러 상태로 전환
          source.close();
          setState((s) => {
            // 이미 완료/에러 상태면 무시
            if (s.step === 3) return s;
            return {
              ...s,
              step: 3 as AppStep,
              error: "서버 연결이 끊어졌습니다. 다시 시도해주세요.",
            };
          });
        }
      );

      eventSourceRef.current = source;
    } catch (e) {
      setState((s) => ({
        ...s,
        step: 1,
        error: e instanceof Error ? e.message : "Upload failed",
      }));
    }
  }, [state.dsdFile, state.docxFile]);

  const cancel = useCallback(async () => {
    if (state.jobId) {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      await cancelJob(state.jobId);
    }
    setState((s) => ({ ...s, step: 1, error: "작업이 취소되었습니다." }));
  }, [state.jobId]);

  const reset = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setState(initialState);
  }, []);

  // 컴포넌트 언마운트 시 SSE 연결 정리
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  return {
    state,
    setDsdFile,
    setDocxFile,
    startProcessing,
    cancel,
    reset,
  };
}
