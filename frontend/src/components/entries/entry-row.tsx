"use client";

import { AlertTriangle, ExternalLink, Eye, EyeOff, MoreHorizontal, Pencil, Trash2, User } from "lucide-react";
import { motion } from "motion/react";
import { CopySecretButton, CopyTextButton } from "@/components/entries/copy-buttons";
import { Checkbox } from "@/components/ui/controls";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menu";
import { Avatar } from "@/components/ui/misc";
import { api, type EntryMeta } from "@/lib/api";
import { cn, relativeTime, safeHost, serviceLetters, serviceStyle } from "@/lib/utils";

export function EntryRow({
  entry,
  vaultId,
  selected,
  onSelect,
  canWrite,
  revealed,
  onToggleReveal,
  onEdit,
  onDelete,
  highlight,
}: {
  entry: EntryMeta;
  vaultId: string;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  canWrite: boolean;
  revealed: string | undefined;
  onToggleReveal: () => void;
  onEdit: () => void;
  onDelete: () => void;
  highlight?: boolean;
}) {
  const link = entry.url ? safeHost(entry.url) : null;
  const shown = revealed !== undefined;

  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.22 }}
      className={cn(
        "group relative grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-4 py-3 transition-colors hover:bg-muted/60 sm:grid-cols-[auto_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.1fr)_auto_auto]",
        selected && "bg-primary/8",
        highlight && "ring-2 ring-primary/50",
      )}
    >
      <Checkbox checked={selected} onCheckedChange={(c) => onSelect(c === true)} aria-label={`Select ${entry.service}`} />

      <button onClick={onEdit} className="flex min-w-0 items-center gap-3 text-left outline-none" aria-label={`Open ${entry.service}`}>
        <Avatar name={entry.service} gradient={serviceStyle(entry.service).background} className="size-10">
          {serviceLetters(entry.service)}
        </Avatar>
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 truncate font-medium">
            {entry.service}
            {entry.corrupt && (
              <span title="This entry could not be decrypted" className="text-danger">
                <AlertTriangle className="size-3.5" />
              </span>
            )}
          </span>
          {link ? (
            <a
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex max-w-full items-center gap-1 truncate text-xs text-muted-foreground hover:text-primary"
            >
              {link.host}
              <ExternalLink className="size-3 shrink-0" />
            </a>
          ) : (
            <span className="block truncate text-xs text-muted-foreground">{entry.notes ? entry.notes : "No URL"}</span>
          )}
        </span>
      </button>

      {/* username */}
      <div className="col-span-2 col-start-2 row-start-2 flex min-w-0 items-center gap-1 sm:col-span-1 sm:col-start-auto sm:row-start-auto">
        {entry.username ? (
          <>
            <User className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm">{entry.username}</span>
            <CopyTextButton text={entry.username} label="Username" />
          </>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </div>

      {/* password */}
      <div className="col-start-3 row-start-1 flex items-center justify-end gap-0.5 sm:col-start-auto sm:row-start-auto sm:justify-start">
        <code
          className={cn(
            "hidden max-w-[11rem] truncate rounded-md px-2 py-1 font-mono text-[13px] sm:inline-block",
            shown ? "bg-primary/10 text-foreground" : "text-muted-foreground",
          )}
        >
          {shown ? revealed : "••••••••••"}
        </code>
        <button
          onClick={onToggleReveal}
          aria-label={shown ? "Hide password" : "Reveal password"}
          className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
        <CopySecretButton label="Password" fetchSecret={async () => (await api.entryPassword(vaultId, entry.id, "copy")).password} />
      </div>

      <span className="hidden text-xs text-muted-foreground sm:block" title={entry.updated_at ? new Date(entry.updated_at * 1000).toLocaleString() : ""}>
        {relativeTime(entry.updated_at)}
      </span>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button aria-label="More actions" className="col-start-3 row-start-2 flex size-8 items-center justify-center justify-self-end rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground sm:col-start-auto sm:row-start-auto">
            <MoreHorizontal className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onEdit}>
            {canWrite ? <Pencil /> : <Eye />} {canWrite ? "Edit" : "View details"}
          </DropdownMenuItem>
          {link && (
            <DropdownMenuItem onSelect={() => window.open(link.href, "_blank", "noopener,noreferrer")}>
              <ExternalLink /> Open website
            </DropdownMenuItem>
          )}
          {canWrite && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem danger onSelect={onDelete}>
                <Trash2 /> Delete
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </motion.li>
  );
}
