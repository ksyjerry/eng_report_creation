"use client";

import { useState } from "react";
import type { LogEntry } from "@/lib/types";
import { downloadResult } from "@/lib/api";
import AgentLog from "./AgentLog";

interface CompletionStepProps {
  jobId: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  logs: LogEntry[];
  onReset: () => void;
}

export default function CompletionStep({
  jobId,
  result,
  error,
  logs,
  onReset,
}: CompletionStepProps) {
  const [showLogs, setShowLogs] = useState(false);
  const isSuccess = !error;

  const handleDownload = async () => {
    if (!jobId) return;
    try {
      await downloadResult(jobId);
    } catch {
      alert("다운로드에 실패했습니다.");
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg border border-gray-200 p-8">
        {/* Status header */}
        <div className="flex items-center gap-3 mb-6">
          {isSuccess ? (
            <>
              <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">생성 완료</h2>
            </>
          ) : (
            <>
              <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">처리 실패</h2>
            </>
          )}
        </div>

        {/* Result summary */}
        {isSuccess && result && (
          <div className="bg-gray-50 rounded-lg p-5 mb-6">
            <h3 className="font-semibold text-gray-900 mb-3">결과 요약</h3>
            {result.summary != null && (
              <p className="text-sm text-gray-700 mb-3">{String(result.summary)}</p>
            )}
            {result.stats != null && typeof result.stats === "object" && (
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(result.stats as Record<string, unknown>).map(([key, val]) => (
                  <div key={key} className="flex justify-between bg-white rounded px-3 py-1.5 border">
                    <span className="text-gray-500">{key}</span>
                    <span className="font-medium text-gray-900">{String(val)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Download button */}
        {isSuccess && (
          <button
            onClick={handleDownload}
            className="w-full py-3.5 rounded-lg bg-[#D04A02] hover:bg-[#B84000] text-white font-medium transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            영문보고서 다운로드
          </button>
        )}

        {/* Log toggle */}
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="mt-4 w-full py-2 text-sm text-gray-500 hover:text-gray-700 flex items-center justify-center gap-1"
        >
          <svg
            className={`w-4 h-4 transition-transform ${showLogs ? "rotate-180" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          상세 로그 {showLogs ? "숨기기" : "보기"}
        </button>

        {showLogs && (
          <div className="mt-2">
            <AgentLog logs={logs} />
          </div>
        )}

        {/* New task button */}
        <button
          onClick={onReset}
          className="mt-4 w-full py-3 rounded-lg border-2 border-gray-300 text-gray-600 hover:bg-gray-50 font-medium transition-colors"
        >
          새 작업 시작
        </button>
      </div>
    </div>
  );
}
