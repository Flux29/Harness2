/**
 * OSS-only CopilotKit over a self-managed AG-UI agent (ADR-0013/0016).
 * Generative UI: named renderer for the harness `write_todos` tool +
 * a catch-all renderer so every other tool (incl. MCP) shows its status.
 */
import { HttpAgent, buildResumeArray, type Interrupt } from "@ag-ui/client";
import { useEffect, useState } from "react";
import {
  CopilotChat,
  CopilotKit,
  useAgent,
  useDefaultRenderTool,
  useRenderTool,
} from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { z } from "zod";

const AGENT_URL = import.meta.env.VITE_AGENT_URL ?? "/agent";

const agent = new HttpAgent({ url: AGENT_URL });

const TodosSchema = z.object({
  todos: z.array(z.looseObject({ content: z.string().optional(), status: z.string().optional() })).optional(),
});

const mark = (s?: string) =>
  s === "completed" ? "✅" : s === "in_progress" ? "🔄" : "⬜";

/** Approval banner for AG-UI interrupts (requires_approval tools, EXECUTE=1).
 *  The run pauses server-side; we show what's pending and resume with the
 *  user's verdict via `agent.runAgent({ resume })`. */
function ApprovalBanner() {
  // CRITICAL: CopilotKit clones self-managed agents — the module-level
  // `agent` object is NOT the instance that runs. useAgent() returns the
  // live clone; subscribe to that, and read interrupts off the event itself.
  const { agent: live } = useAgent();
  const [pending, setPending] = useState<Interrupt[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Restore unanswered interrupts after page reload — otherwise the thread
    // is stuck: new messages fail with "pending interrupt(s) not addressed".
    if (live.pendingInterrupts.length) setPending([...live.pendingInterrupts]);
    const sub = live.subscribe({
      onRunFinishedEvent({ event, agent: a }: any) {
        const fromEvent: Interrupt[] = event?.outcome?.type === "interrupt" ? (event.outcome.interrupts ?? []) : [];
        setPending(fromEvent.length ? fromEvent : [...(a?.pendingInterrupts ?? [])]);
      },
      onRunErrorEvent() {
        setPending([]);
      },
    });
    return () => sub.unsubscribe();
  }, [live]);

  if (pending.length === 0) return null;

  const describe = (i: Interrupt): string => {
    const tcId = (i as any).toolCallId ?? (i as any).tool_call_id;
    for (const m of live.messages as any[]) {
      for (const tc of m?.toolCalls ?? []) {
        if (tc.id === tcId) return `${tc.function?.name}(${tc.function?.arguments ?? ""})`;
      }
    }
    return i.reason ?? "tool call";
  };

  const answer = async (approved: boolean) => {
    if (busy) return; // double-click guard: a stale resume is a server-side UserError
    setBusy(true);
    const responses = Object.fromEntries(
      pending.map((i) => [
        i.id,
        { status: "resolved" as const, payload: approved ? { approved: true } : { approved: false, reason: "Denied by user" } },
      ]),
    );
    const resume = buildResumeArray(pending, responses);
    setPending([]);
    try {
      await live.runAgent({ resume });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ border: "2px solid #e0a800", background: "#fff8e1", borderRadius: 8, padding: 12, margin: 8 }}>
      <strong>⚠️ Agent is asking permission to run:</strong>
      <ul style={{ margin: "6px 0" }}>
        {pending.map((i) => (
          <li key={i.id}><code style={{ whiteSpace: "pre-wrap" }}>{describe(i)}</code></li>
        ))}
      </ul>
      <button disabled={busy} onClick={() => answer(true)} style={{ marginRight: 8, padding: "4px 14px", cursor: "pointer" }}>
        ✅ Approve
      </button>
      <button disabled={busy} onClick={() => answer(false)} style={{ padding: "4px 14px", cursor: "pointer" }}>
        ❌ Deny
      </button>
    </div>
  );
}

function Chat() {
  // Named renderer: the harness's planning tool becomes a live checklist.
  useRenderTool({
    name: "write_todos",
    parameters: TodosSchema,
    render: ({ status, parameters }) => {
      const todos = parameters?.todos ?? [];
      return (
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: "8px 12px", margin: "4px 0" }}>
          <strong>{status !== "complete" ? "Planning…" : "Plan"}</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 4, listStyle: "none" }}>
            {todos.map((t, i) => (
              <li key={i}>
                {mark(t.status)} {t.content ?? JSON.stringify(t)}
              </li>
            ))}
          </ul>
        </div>
      );
    },
  });

  // Catch-all: every other tool (filesystem, subagents, forks, MCP) gets a
  // compact status card instead of raw JSON.
  useDefaultRenderTool({
    render: ({ name, status, result }) => (
      <div style={{ fontFamily: "monospace", fontSize: 13, opacity: 0.85, margin: "2px 0" }}>
        {status === "complete" ? "✓" : "⏳"} {name}
        {status === "complete" && result != null && (
          <details style={{ display: "inline-block", marginLeft: 8 }}>
            <summary style={{ cursor: "pointer" }}>result</summary>
            <pre style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
              {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
            </pre>
          </details>
        )}
      </div>
    ),
  });

  return (
    <main style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <ApprovalBanner />
      <CopilotChat
        labels={{ welcomeMessageText: "Deep agent ready — plans, forks, files, MCP tools." }}
        style={{ flex: 1, minHeight: 0 }}
      />
    </main>
  );
}

export default function App() {
  return (
    <CopilotKit selfManagedAgents={{ default: agent }}>
      <Chat />
    </CopilotKit>
  );
}
