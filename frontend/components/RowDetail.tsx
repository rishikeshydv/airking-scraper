"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { BUILDING_TYPES, meetingPdfUrl, postCorrection, type AgendaItem } from "@/lib/api";
import { CORRECTABLE_FIELDS, fieldInputText, formatFieldValue, parseFieldInput, type FieldKind } from "@/lib/corrections";
import type { AgendaGroup } from "@/lib/grouping";

const linkClass = "text-blue-600 underline dark:text-blue-400";
const inputClass = "rounded border border-black/15 bg-transparent px-2 py-0.5 text-sm dark:border-white/15";
const buttonClass = "rounded border border-black/15 px-2 py-0.5 text-xs hover:bg-black/[.05] dark:border-white/15 dark:hover:bg-white/[.08]";

// No login in this tool, so corrected_by is a name the user types once; it's
// remembered in this browser only.
const CORRECTED_BY_STORAGE_KEY = "airking.correctedBy";

function readSavedName(): string {
  try {
    return localStorage.getItem(CORRECTED_BY_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveName(name: string): void {
  try {
    localStorage.setItem(CORRECTED_BY_STORAGE_KEY, name);
  } catch {
    // Storage unavailable (private window, blocked site data): the name just isn't remembered.
  }
}

interface FieldInputProps {
  kind: FieldKind;
  value: string;
  onChange: (value: string) => void;
}

function FieldInput({ kind, value, onChange }: FieldInputProps) {
  if (kind === "building_type") {
    return (
      <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {BUILDING_TYPES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
    );
  }
  if (kind === "yes_no") {
    return (
      <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        <option value="yes">Yes</option>
        <option value="no">No</option>
      </select>
    );
  }
  return (
    <input
      className={inputClass}
      type="text"
      inputMode={kind === "integer" ? "numeric" : "text"}
      placeholder={kind === "codes" ? "c, d1" : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

interface CorrectableFieldProps {
  item: AgendaItem;
  field: (typeof CORRECTABLE_FIELDS)[number]["field"];
  label: string;
  kind: FieldKind;
}

function CorrectableField({ item, field, label, kind }: CorrectableFieldProps) {
  const queryClient = useQueryClient();
  const correction = item.overrides[field];
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: postCorrection,
    onSuccess: () => {
      setIsEditing(false);
      return queryClient.invalidateQueries({ queryKey: ["agenda-items"] });
    },
  });

  function startEditing() {
    setDraft(fieldInputText(kind, item[field]));
    setName(readSavedName());
    setInputError(null);
    mutation.reset();
    setIsEditing(true);
  }

  function save() {
    const parsed = parseFieldInput(kind, draft);
    if ("error" in parsed) {
      setInputError(parsed.error);
      return;
    }
    const correctedBy = name.trim();
    if (!correctedBy) {
      setInputError("Enter your name");
      return;
    }
    saveName(correctedBy);
    mutation.mutate({ itemId: item.id, field, value: parsed.value, correctedBy });
  }

  function resetToExtracted() {
    mutation.mutate({ itemId: item.id, field, value: null, correctedBy: readSavedName() });
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <span className="w-28 text-black/50 dark:text-white/50">{label}</span>

      {isEditing ? (
        <>
          <FieldInput kind={kind} value={draft} onChange={setDraft} />
          <input
            className={`${inputClass} w-32`}
            type="text"
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className={buttonClass} disabled={mutation.isPending} onClick={save}>
            Save
          </button>
          <button className={buttonClass} onClick={() => setIsEditing(false)}>
            Cancel
          </button>
          {(inputError ?? mutation.error?.message) && (
            <span className="text-red-600 dark:text-red-400">{inputError ?? mutation.error?.message}</span>
          )}
        </>
      ) : (
        <>
          <span className="text-sm">{formatFieldValue(item[field])}</span>
          {correction && (
            <span className="text-black/50 dark:text-white/50">
              corrected by {correction.corrected_by}
              {correction.corrected_at && ` on ${correction.corrected_at.slice(0, 10)}`} · extracted:{" "}
              {formatFieldValue(correction.raw)}
            </span>
          )}
          <button className={buttonClass} onClick={startEditing}>
            Edit
          </button>
          {correction && (
            <button className={buttonClass} disabled={mutation.isPending} onClick={resetToExtracted}>
              Reset
            </button>
          )}
          {mutation.error && <span className="text-red-600 dark:text-red-400">{mutation.error.message}</span>}
        </>
      )}
    </div>
  );
}

export function RowDetail({ group }: { group: AgendaGroup }) {
  return (
    <div className="flex flex-col gap-4">
      {group.history.map((item) => (
        <div key={item.id} className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-black/50 dark:text-white/50">
            <span>{item.meeting.meeting_date}</span>
            <span>·</span>
            <span className="capitalize">
              {item.meeting.town} {item.meeting.board}
            </span>
            <span>·</span>
            <span>{item.agenda_section ?? "no section"}</span>
            {item.application_id && (
              <>
                <span>·</span>
                <span>{item.application_id}</span>
              </>
            )}
            {item.meeting.source_pdf_url && (
              <a className={linkClass} href={meetingPdfUrl(item.meeting.source_pdf_url)} target="_blank" rel="noopener noreferrer">
                source PDF
              </a>
            )}
            {item.meeting.google_drive_url && (
              <a className={linkClass} href={item.meeting.google_drive_url} target="_blank" rel="noopener noreferrer">
                Drive folder
              </a>
            )}
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {item.project_text || (
              <span className="italic text-black/40 dark:text-white/40">No project narrative in source.</span>
            )}
          </p>
          {item.variances_raw && (
            <p className="text-xs text-black/60 dark:text-white/60">Variances: {item.variances_raw}</p>
          )}
          <div className="mt-1 flex flex-col gap-1">
            {CORRECTABLE_FIELDS.map(({ field, label, kind }) => (
              <CorrectableField key={field} item={item} field={field} label={label} kind={kind} />
            ))}
          </div>
          {item.extraction_confidence !== null && (
            <p className="text-xs text-black/40 dark:text-white/40">
              Extraction confidence: {Math.round(item.extraction_confidence * 100)}%
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
