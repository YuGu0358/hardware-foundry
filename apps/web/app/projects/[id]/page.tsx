"use client";

import { use, useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../../../lib/api";
import type { Message, ProductSpec, ProjectDetail } from "../../../lib/types";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState<"idle" | "reply" | "plan" | "approve">("idle");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDetail(await api.getProject(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function sendReply() {
    if (!reply.trim()) return;
    setBusy("reply");
    setError(null);
    try {
      const next = await api.postMessage(id, reply.trim());
      setDetail(next);
      setReply("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("idle");
    }
  }

  async function runCommand(kind: "plan" | "approve") {
    setBusy(kind);
    setError(null);
    try {
      const next = kind === "plan" ? await api.startPlanning(id) : await api.approvePlan(id);
      setDetail(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("idle");
    }
  }

  if (!detail) {
    return <p className="text-sm text-zinc-500">Loading project…</p>;
  }

  const state = detail.state;
  const phase = state.current_phase;
  const spec = state.product_spec;
  const canPlan = !state.user_intent_to_plan && state.clarification_history.length > 0;
  const canApprove = !!spec && !state.gate_plan_approved;

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <section className="space-y-4">
        <header className="flex items-baseline justify-between">
          <h1 className="text-lg font-semibold">{detail.project.title ?? detail.project.raw_input}</h1>
          <span className="rounded-full bg-zinc-100 px-2 py-1 text-xs uppercase tracking-wide text-zinc-700">
            {phase}
          </span>
        </header>

        <div className="rounded-md border border-zinc-200 bg-white">
          <div className="space-y-4 px-4 py-3">
            <ChatBubble role="user" content={state.raw_input} />
            {state.clarification_history.map((m, i) => (
              <ChatBubble key={i} role={m.role} content={m.content} />
            ))}
          </div>
        </div>

        {!state.gate_plan_approved && (
          <div className="space-y-3">
            <textarea
              rows={3}
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Type your answers, one per line if multiple…"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
            <div className="flex flex-wrap gap-2">
              <button
                onClick={sendReply}
                disabled={busy !== "idle" || !reply.trim()}
                className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
              >
                {busy === "reply" ? "Sending…" : "Send reply"}
              </button>
              {canPlan && (
                <button
                  onClick={() => runCommand("plan")}
                  disabled={busy !== "idle"}
                  className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {busy === "plan" ? "Planning…" : "OK, start planning"}
                </button>
              )}
              {canApprove && (
                <button
                  onClick={() => runCommand("approve")}
                  disabled={busy !== "idle"}
                  className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {busy === "approve" ? "Approving…" : "Approve ProductSpec"}
                </button>
              )}
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
          </div>
        )}

        {state.gate_plan_approved && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
            ✅ ProductSpec frozen. Phase 1 complete — Phase 2 (Compliance + Feasibility) is next.
          </div>
        )}
      </section>

      <aside className="space-y-4">
        {state.reference_findings && state.reference_findings.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-zinc-700">Reference products</h2>
            <ul className="mt-2 space-y-2">
              {state.reference_findings.map((r) => (
                <li key={r.url} className="rounded-md border border-zinc-200 bg-white p-3 text-xs">
                  <div className="flex items-baseline justify-between">
                    <a href={r.url} target="_blank" rel="noreferrer" className="font-medium text-zinc-900 hover:underline">
                      {r.name}
                    </a>
                    <span className="text-zinc-500">{(r.similarity_score * 100).toFixed(0)}%</span>
                  </div>
                  <p className="mt-1 text-zinc-600">{r.summary}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {spec && <SpecCard spec={spec} />}
      </aside>
    </div>
  );
}

function ChatBubble({ role, content }: { role: Message["role"]; content: string }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-md px-3 py-2 text-sm ${
          isUser ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-900"
        }`}
      >
        <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function SpecCard({ spec }: { spec: ProductSpec }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <h2 className="text-sm font-semibold text-zinc-700">{spec.title}</h2>
      <p className="mt-1 text-xs text-zinc-600">{spec.summary}</p>
      <p className="mt-2 text-xs italic text-zinc-500">Use case: {spec.target_use_case}</p>

      <div className="mt-3">
        <h3 className="text-xs font-semibold text-zinc-700">Requirements ({spec.requirements.length})</h3>
        <ul className="mt-1 space-y-1 text-xs">
          {spec.requirements.map((r) => (
            <li key={r.id} className="flex gap-2">
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                  r.priority === "must"
                    ? "bg-red-100 text-red-700"
                    : r.priority === "should"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-zinc-100 text-zinc-600"
                }`}
              >
                {r.priority}
              </span>
              <span className="text-zinc-700">{r.statement}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-3 text-xs">
        <h3 className="font-semibold text-zinc-700">Constraints</h3>
        <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-zinc-600">
          {spec.constraints.max_dimensions_mm && (
            <>
              <dt>Max dims (mm)</dt>
              <dd>{spec.constraints.max_dimensions_mm.join(" × ")}</dd>
            </>
          )}
          {spec.constraints.max_weight_g != null && (
            <>
              <dt>Max weight</dt>
              <dd>{spec.constraints.max_weight_g} g</dd>
            </>
          )}
          {spec.constraints.max_power_w != null && (
            <>
              <dt>Max power</dt>
              <dd>{spec.constraints.max_power_w} W</dd>
            </>
          )}
          {spec.constraints.target_bom_cost_cents != null && (
            <>
              <dt>Target BOM</dt>
              <dd>{(spec.constraints.target_bom_cost_cents / 100).toFixed(2)}</dd>
            </>
          )}
          <dt>Markets</dt>
          <dd>{spec.constraints.compliance_markets.join(", ") || "—"}</dd>
        </dl>
      </div>
    </div>
  );
}
