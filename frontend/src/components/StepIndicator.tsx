"use client";

import type { AppStep } from "@/lib/types";

interface StepIndicatorProps {
  currentStep: AppStep;
}

const steps = [
  { number: 1, label: "파일 업로드" },
  { number: 2, label: "생성 중" },
  { number: 3, label: "완료" },
];

export default function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-0 py-8">
      {steps.map((step, idx) => {
        const isActive = step.number === currentStep;
        const isCompleted = step.number < currentStep;

        return (
          <div key={step.number} className="flex items-center">
            {/* Circle */}
            <div className="flex flex-col items-center">
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors ${
                  isActive
                    ? "border-[#D04A02] bg-[#D04A02] text-white"
                    : isCompleted
                    ? "border-[#D04A02] bg-[#D04A02] text-white"
                    : "border-gray-300 bg-white text-gray-400"
                }`}
              >
                {isCompleted ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  step.number
                )}
              </div>
              <span
                className={`mt-2 text-xs font-medium ${
                  isActive ? "text-[#D04A02]" : isCompleted ? "text-[#D04A02]" : "text-gray-400"
                }`}
              >
                {step.label}
              </span>
            </div>

            {/* Connector line */}
            {idx < steps.length - 1 && (
              <div
                className={`w-24 h-0.5 mx-2 mt-[-1.2rem] ${
                  step.number < currentStep ? "bg-[#D04A02]" : "bg-gray-300"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
