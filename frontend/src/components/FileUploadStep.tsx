"use client";

import FileUploadZone from "./FileUploadZone";

interface FileUploadStepProps {
  dsdFile: File | null;
  docxFile: File | null;
  onDsdSelect: (file: File | null) => void;
  onDocxSelect: (file: File | null) => void;
  onStart: () => void;
  error: string | null;
}

export default function FileUploadStep({
  dsdFile,
  docxFile,
  onDsdSelect,
  onDocxSelect,
  onStart,
  error,
}: FileUploadStepProps) {
  const canStart = dsdFile !== null && docxFile !== null;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* File upload card */}
      <div className="bg-white rounded-lg border border-gray-200 p-8">
        <div className="flex gap-8">
          <FileUploadZone
            title="당기 국문 재무제표"
            description="당기 DSD 파일을 업로드하세요"
            accept=".dsd,.zip"
            acceptLabel=".dsd 파일"
            onFileSelect={onDsdSelect}
            selectedFile={dsdFile}
          />
          <FileUploadZone
            title="전기 영문 재무제표"
            description="전기 영문 DOCX 또는 PDF 파일을 업로드하세요"
            accept=".docx,.pdf"
            acceptLabel=".docx 또는 .pdf"
            onFileSelect={onDocxSelect}
            selectedFile={docxFile}
          />
        </div>

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Start button */}
        <button
          onClick={onStart}
          disabled={!canStart}
          className={`mt-6 w-full py-3.5 rounded-lg text-base font-medium transition-colors ${
            canStart
              ? "bg-[#D04A02] hover:bg-[#B84000] text-white cursor-pointer"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          }`}
        >
          영문보고서 생성
        </button>
      </div>

      {/* Instructions card */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-3">사용 방법</h3>
        <ol className="text-sm text-gray-600 space-y-1.5 list-decimal list-inside">
          <li>당기 국문 DSD 파일(.dsd)과 전기 영문 재무제표(.docx 또는 .pdf)를 업로드합니다.</li>
          <li><strong>영문보고서 생성</strong> 버튼을 클릭하면 AI Agent가 당기 영문 재무제표를 자동 생성합니다.</li>
          <li>완료 후 생성된 당기 영문보고서를 다운로드하여 확인합니다.</li>
        </ol>
        <p className="mt-3 text-sm text-gray-500">
          전기 영문보고서의 서식과 번역을 최대한 재사용하여, 변경분만 최소 조정합니다.
        </p>
        <p className="mt-1 text-sm text-red-600 font-medium">
          생성 과정이 10분 이상 소요될 수 있습니다. 완료될 때까지 기다려주세요.
        </p>
      </div>
    </div>
  );
}
