import React from "react";
import { CircleDot, ScanLine, ShieldCheck, Waypoints, GitFork, FileText } from "lucide-react";

const icons = {
  orchestrator: Waypoints,
  planning: GitFork,
  analysis: ScanLine,
  validation: ShieldCheck,
  reporting: FileText,
};
export function AgentIcon({ role, size = 20 }) {
  const Icon = icons[role] || CircleDot;
  return <Icon size={size} strokeWidth={1.65} />;
}
