"use client";

import { useMutation } from "@tanstack/react-query";
import { Bot, CornerDownLeft, Sparkles, User } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type AdvisorAnswer, type IntelRef } from "@/lib/api";
import { cn } from "@/lib/utils";

type Msg = { role: "user"; text: string } | { role: "advisor"; answer: AdvisorAnswer };

const STARTERS = ["How secure am I?", "What should I fix today?", "Which passwords are reused?", "Which accounts have no two-factor?", "Am I in a breach?", "Is paypa1.com safe?"];

/**
 * A conversation on top of the security engine. It answers from your vault's verdicts (scores, counts, names),
 * which contain no passwords, so there is nothing sensitive to leak. It is not a general chatbot.
 */
export function Advisor({ onOpen }: { onOpen: (ref: IntelRef) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>(STARTERS);
  const end = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => api.advisor(q),
    onSuccess: (a) => {
      setMsgs((m) => [...m, { role: "advisor", answer: a }]);
      setSuggestions(a.suggestions.length ? a.suggestions : STARTERS);
    },
    onError: (e) =>
      setMsgs((m) => [...m, { role: "advisor", answer: { intent: "error", answer: e instanceof ApiError ? e.message : "Something went wrong.", bullets: [], refs: [], suggestions: [] } }]),
  });

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, ask.isPending]);

  function send(q: string) {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setText("");
    ask.mutate(question);
  }

  return (
    <div className="glass flex h-[34rem] flex-col overflow-hidden rounded-3xl">
      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {msgs.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="gradient-bg mb-4 flex size-14 items-center justify-center rounded-2xl text-white shadow-lg">
              <Sparkles className="size-7" />
            </span>
            <h3 className="text-lg font-semibold tracking-tight">Ask about your security</h3>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              I answer from your vault&apos;s security verdicts: never from your passwords. Everything is computed on this server and nothing is sent to an outside AI.
            </p>
          </div>
        )}
        <AnimatePresence initial={false}>
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end gap-2.5">
                <div className="gradient-bg max-w-[80%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm text-white">{m.text}</div>
                <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted"><User className="size-4" /></span>
              </motion.div>
            ) : (
              <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2.5">
                <span className="gradient-bg mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-white"><Bot className="size-4" /></span>
                <div className="max-w-[85%] space-y-2.5">
                  <div className="rounded-2xl rounded-tl-md bg-muted px-4 py-2.5 text-sm leading-relaxed">{m.answer.answer}</div>
                  {m.answer.bullets.length > 0 && (
                    <ul className="space-y-1.5 rounded-2xl border px-4 py-3 text-sm">
                      {m.answer.bullets.map((b, k) => (
                        <li key={k} className="flex gap-2">
                          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
                          <span className="text-foreground/90">{b}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {m.answer.refs.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.answer.refs.slice(0, 5).map((r) => (
                        <button key={r.id} onClick={() => onOpen(r)} className="rounded-full border px-3 py-1 text-xs font-medium transition hover:bg-muted">
                          Open {r.service}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            ),
          )}
        </AnimatePresence>
        {ask.isPending && (
          <div className="flex gap-2.5">
            <span className="gradient-bg flex size-7 shrink-0 items-center justify-center rounded-full text-white"><Bot className="size-4" /></span>
            <div className="flex items-center gap-1 rounded-2xl bg-muted px-4 py-3">
              {[0, 1, 2].map((d) => (
                <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${d * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="border-t p-3">
        <div className={cn("mb-2.5 flex flex-wrap gap-1.5", msgs.length > 0 && "max-h-8 overflow-hidden")}>
          {suggestions.slice(0, 6).map((s) => (
            <button key={s} onClick={() => send(s)} className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
              {s}
            </button>
          ))}
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask anything about your security…" aria-label="Ask the security advisor" maxLength={300} />
          <Button type="submit" size="icon" aria-label="Send" disabled={!text.trim()} loading={ask.isPending}>
            <CornerDownLeft />
          </Button>
        </form>
      </div>
    </div>
  );
}
