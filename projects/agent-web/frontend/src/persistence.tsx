/**
 * Manual thread persistence (ISSUE-4, ADR-0023), built on NATIVE seams:
 *
 * - `PersistentAgent` implements `HttpAgent`'s `connect()` lifecycle —
 *   CopilotChat calls `connectAgent` on mount AND on every explicit-thread
 *   change, so transcript + pending-interrupt rehydration ride the
 *   framework's own flow (MESSAGES_SNAPSHOT re-renders natively; a
 *   RUN_FINISHED interrupt outcome repopulates `pendingInterrupts`, which the
 *   existing ApprovalBanner already handles).
 * - `ThreadSidebar` is hand-rolled ONLY because `CopilotThreadsDrawer`'s
 *   list fetch is license-gated (Enterprise Intelligence); it drives the same
 *   provider-controlled thread switching.
 */
import { HttpAgent } from "@ag-ui/client";
import type { BaseEvent, RunAgentInput } from "@ag-ui/core";
import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";
import { Observable } from "rxjs";

export interface ThreadItem {
  id: string;
  updated_at: string;
  message_count: number;
  title: string;
  has_pending_interrupts: boolean;
  running: boolean;
}

export class PersistentAgent extends HttpAgent {
  /** Rehydrate the active thread from the server-authoritative history. */
  protected connect(input: RunAgentInput): Observable<BaseEvent> {
    return new Observable<BaseEvent>((sub) => {
      const ctrl = new AbortController();
      (async () => {
        sub.next({
          type: "RUN_STARTED", threadId: input.threadId, runId: input.runId,
        } as unknown as BaseEvent);
        let messages: unknown[] = [];
        let interrupts: unknown[] = [];
        try {
          const r = await fetch(
            `/threads/${encodeURIComponent(input.threadId)}/messages`,
            { headers: this.headers, signal: ctrl.signal },
          );
          if (r.ok) {
            const body = await r.json();
            messages = body.messages ?? [];
            interrupts = body.interrupts ?? [];
          }
          // 404 = a brand-new thread: fall through to the empty snapshot,
          // which also scrubs any stale transcript from the previous thread.
        } catch {
          // Backend unreachable: hydrate empty rather than wedge the chat.
        }
        sub.next({ type: "MESSAGES_SNAPSHOT", messages } as unknown as BaseEvent);
        sub.next({
          type: "RUN_FINISHED", threadId: input.threadId, runId: input.runId,
          ...(interrupts.length
            ? { outcome: { type: "interrupt", interrupts } }
            : {}),
        } as unknown as BaseEvent);
        sub.complete();
      })().catch((e) => sub.error(e));
      return () => ctrl.abort();
    });
  }
}

/** Hand-rolled thread list driving the native provider-controlled threadId. */
export function ThreadSidebar({
  activeId,
  onSelect,
  onNew,
}: {
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const { agent: live } = useAgent();
  const [threads, setThreads] = useState<ThreadItem[]>([]);

  const refresh = () => {
    fetch("/threads")
      .then((r) => (r.ok ? r.json() : { threads: [] }))
      .then((b) => setThreads(b.threads ?? []))
      .catch(() => {});
  };

  useEffect(() => {
    refresh();
    // New threads/titles/running flags appear after each run settles (the
    // hydration connect fires this too — a harmless extra refresh).
    const sub = live.subscribe({
      onRunFinishedEvent: refresh,
      onRunErrorEvent: refresh,
    } as never);
    return () => sub.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  const clearPendingAndGo = (fn: () => void) => {
    // Navigating away from an interrupted thread: connectAgent throws on a
    // non-empty pendingInterrupts ("pending interrupt(s) not addressed"), so
    // clear the LIVE clone's list first. The interrupt itself is not lost —
    // it is server-derived and replays when the thread is reopened.
    live.pendingInterrupts = [];
    fn();
  };

  return (
    <aside style={{
      width: 260, flexShrink: 0, borderRight: "1px solid #ddd",
      overflowY: "auto", padding: 8, fontSize: 14,
    }}>
      <button
        onClick={() => clearPendingAndGo(onNew)}
        style={{ width: "100%", padding: "6px 0", marginBottom: 8, cursor: "pointer" }}
      >
        + New thread
      </button>
      {threads.map((t) => (
        <div
          key={t.id}
          onClick={() => t.id !== activeId && clearPendingAndGo(() => onSelect(t.id))}
          style={{
            padding: "6px 8px", borderRadius: 6, cursor: "pointer",
            marginBottom: 2, lineHeight: 1.3,
            background: t.id === activeId ? "#e8f0fe" : "transparent",
          }}
        >
          <div style={{
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {t.running ? "⏳ " : ""}{t.has_pending_interrupts ? "⚠️ " : ""}{t.title}
          </div>
          <small style={{ opacity: 0.6 }}>
            {t.message_count} msgs · {new Date(t.updated_at).toLocaleString()}
          </small>
        </div>
      ))}
    </aside>
  );
}
