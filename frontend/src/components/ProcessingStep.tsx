"use client";

import type { LogEntry } from "@/lib/types";
import AgentLog from "./AgentLog";
import ProgressBar from "./ProgressBar";

interface ProcessingStepProps {
  logs: LogEntry[];
  progress: number;
  currentStep: string;
  onCancel: () => void;
}

export default function ProcessingStep({
  logs,
  progress,
  currentStep,
  onCancel,
}: ProcessingStepProps) {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg border border-gray-200 p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-5 h-5 border-2 border-[#D04A02] border-t-transparent rounded-full animate-spin" />
          <h2 className="text-lg font-semibold text-gray-900">영문보고서 생성 중...</h2>
        </div>

        <ProgressBar progress={progress} />

        {currentStep && (
          <p className="mt-3 text-sm text-gray-600">
            현재 작업: {currentStep}
          </p>
        )}

        <div className="mt-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Agent 로그</h3>
          <AgentLog logs={logs} />
        </div>

        <button
          onClick={onCancel}
          className="mt-6 w-full py-3 rounded-lg border-2 border-gray-300 text-gray-600 hover:bg-gray-50 font-medium transition-colors"
        >
          생성 중단
        </button>
      </div>
    </div>
  );
}
