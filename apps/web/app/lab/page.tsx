"use client";

import { AccessDenied } from "../../features/auth/AccessDenied";
import { TestLabHome } from "../../features/lab/TestLabHome";
import { pcRoleLabEnabled } from "../../lib/auth/config";

export default function LabPage() {
  if (!pcRoleLabEnabled) return <AccessDenied message="The PC Test Lab is available only in the controlled local QA build." />;
  return <TestLabHome />;
}
