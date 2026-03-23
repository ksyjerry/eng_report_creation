"use client";

import Image from "next/image";

export default function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
      <div className="flex items-center gap-3">
        <Image src="/pwc-logo.png" alt="PwC" width={72} height={28} priority />
        <span className="border-l border-gray-300 h-6 mx-1" />
        <span className="font-bold text-lg text-gray-900">SARA</span>
        <span className="border-l border-gray-300 h-6 mx-1" />
        <span className="text-gray-600 text-sm">영문보고서 Agent</span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <span className="italic text-gray-400">Developed by Assurance DA</span>
      </div>
    </header>
  );
}
