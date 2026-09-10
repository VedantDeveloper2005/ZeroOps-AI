"use client";

import { useEffect, useRef, useState } from "react";
import type { Project } from "./api";

export function useProjectSelection(projects: Project[], requestedProject: string | null) {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const previousRequest = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    // Wait for the project list before consuming a deep link. Once consumed,
    // retain manual selections until the URL actually names a different project.
    if (projects.length === 0) {
      setSelectedProjectId("");
      return;
    }
    const requestChanged = requestedProject !== previousRequest.current;
    previousRequest.current = requestedProject;
    setSelectedProjectId((current) => {
      if (requestChanged && requestedProject && projects.some((project) => project.id === requestedProject)) {
        return requestedProject;
      }
      if (projects.some((project) => project.id === current)) return current;
      return projects[0].id;
    });
  }, [projects, requestedProject]);

  return [selectedProjectId, setSelectedProjectId] as const;
}
