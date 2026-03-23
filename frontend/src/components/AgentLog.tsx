"use client";

import { useEffect, useRef } from "react";
import type { LogEntry } from "@/lib/types";

interface AgentLogProps {
  logs: LogEntry[];
}

const levelColors: Record<string, string> = {
  info: "text-gray-700",
  warning: "text-[#D04A02]",
  error: "text-red-600",
  success: "text-green-600",
};

const levelIcons: Record<string, string> = {
  info: "",
  warning: "\u26A0",
  error: "\u2717",
  success: "\u2713",
};

export default function AgentLog({ logs }: AgentLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-80 overflow-y-auto font-mono text-xs leading-5">
      {logs
        .filter((l) => l.type === "log")
        .map((log, i) => {
          const color = levelColors[log.level || "info"] || "text-gray-400";
          const icon = levelIcons[log.level || "info"] || "";
          return (
            <div key={i} className={`${color.replace("text-", "text-")} flex gap-2`}>
              <span className="text-gray-500 shrink-0">
                [{log.timestamp || "--:--:--"}]
              </span>
              {icon && <span>{icon}</span>}
              <span className={color.replace("text-gray-700", "text-gray-300").replace("text-[#D04A02]", "text-orange-400").replace("text-red-600", "text-red-400").replace("text-green-600", "text-green-400")}>
                {log.message}
              </span>
            </div>
          );
        })}
      <div ref={bottomRef} />
    </div>
  );
}
