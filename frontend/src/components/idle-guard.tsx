"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Timer } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const WARN_SECS = 60;

/**
 * Locks the vault when the person walks away. Idle time is measured here, in the browser; the server
 * enforces its own limit too. A minute before the end we warn, so a long read is never a surprise.
 */
export function IdleGuard({ timeoutSecs }: { timeoutSecs: number }) {
  const qc = useQueryClient();
  const last = useRef(Date.now());
  const [remaining, setRemaining] = useState<number | null>(null);

  const touch = useCallback(() => {
    last.current = Date.now();
  }, []);

  const lock = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      qc.clear();
      qc.setQueryData(["status"], { initialized: true, org_name: "", me: null, idle_timeout_secs: timeoutSecs });
      window.location.assign("/login");
    }
  }, [qc, timeoutSecs]);

  useEffect(() => {
    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    let lastMove = 0;
    const onMove = () => {
      const now = Date.now();
      if (now - lastMove > 1000) {
        lastMove = now;
        touch();
      }
    };
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    window.addEventListener("pointermove", onMove, { passive: true });

    const tick = setInterval(() => {
      const idle = (Date.now() - last.current) / 1000;
      const left = Math.ceil(timeoutSecs - idle);
      if (left <= 0) void lock();
      else setRemaining(left <= WARN_SECS ? left : null);
    }, 1000);

    // Tell the server the user is still here (its clock runs separately from ours).
    const ping = setInterval(() => {
      const idle = (Date.now() - last.current) / 1000;
      api.ping(idle).catch(() => undefined); // a 401 is handled globally: the shell locks itself
    }, 30_000);

    return () => {
      events.forEach((e) => window.removeEventListener(e, touch));
      window.removeEventListener("pointermove", onMove);
      clearInterval(tick);
      clearInterval(ping);
    };
  }, [timeoutSecs, touch, lock]);

  return (
    <Dialog open={remaining !== null} onOpenChange={(o) => !o && touch()}>
      <DialogContent hideClose className="max-w-sm text-center">
        <DialogHeader className="items-center pr-0">
          <div className="gradient-bg mb-2 flex size-14 items-center justify-center rounded-2xl text-white">
            <Timer className="size-7" />
          </div>
          <DialogTitle>Still there?</DialogTitle>
          <DialogDescription>
            For your security this vault locks in <b className="tabular-nums text-foreground">{remaining}s</b>.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="sm:justify-center">
          <Button variant="outline" onClick={() => void lock()}>
            Lock now
          </Button>
          <Button
            onClick={() => {
              touch();
              api.ping(0).catch(() => undefined);
            }}
          >
            Stay signed in
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
