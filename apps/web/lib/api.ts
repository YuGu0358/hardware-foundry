import type { ProjectDetail, ProjectSummary } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => jsonFetch<{ status: string; version: string }>("/api/v1/healthz"),

  listProjects: () => jsonFetch<ProjectSummary[]>("/api/v1/projects"),

  createProject: (raw_input: string, title?: string) =>
    jsonFetch<ProjectDetail>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({ raw_input, title }),
    }),

  getProject: (id: string) => jsonFetch<ProjectDetail>(`/api/v1/projects/${id}`),

  postMessage: (id: string, content: string) =>
    jsonFetch<ProjectDetail>(`/api/v1/projects/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  startPlanning: (id: string) =>
    jsonFetch<ProjectDetail>(`/api/v1/projects/${id}/commands/start-planning`, {
      method: "POST",
    }),

  approvePlan: (id: string) =>
    jsonFetch<ProjectDetail>(`/api/v1/projects/${id}/commands/approve-plan`, {
      method: "POST",
    }),
};
