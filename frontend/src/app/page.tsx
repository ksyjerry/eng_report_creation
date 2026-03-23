"use client";

import StepIndicator from "@/components/StepIndicator";
import FileUploadStep from "@/components/FileUploadStep";
import ProcessingStep from "@/components/ProcessingStep";
import CompletionStep from "@/components/CompletionStep";
import { useConversionState } from "@/hooks/useConversionState";

export default function Home() {
  const { state, setDsdFile, setDocxFile, startProcessing, cancel, reset } =
    useConversionState();

  return (
    <div>
      <StepIndicator currentStep={state.step} />

      {state.step === 1 && (
        <FileUploadStep
          dsdFile={state.dsdFile}
          docxFile={state.docxFile}
          onDsdSelect={setDsdFile}
          onDocxSelect={setDocxFile}
          onStart={startProcessing}
          error={state.error}
        />
      )}

      {state.step === 2 && (
        <ProcessingStep
          logs={state.logs}
          progress={state.progress}
          currentStep={state.currentStep}
          onCancel={cancel}
        />
      )}

      {state.step === 3 && (
        <CompletionStep
          jobId={state.jobId}
          result={state.result}
          error={state.error}
          logs={state.logs}
          onReset={reset}
        />
      )}
    </div>
  );
}
