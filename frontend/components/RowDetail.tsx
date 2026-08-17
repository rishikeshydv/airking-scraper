import type { AgendaGroup } from "@/lib/grouping";
import { meetingPdfUrl } from "@/lib/api";

const linkClass = "text-blue-600 underline dark:text-blue-400";

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
          {item.variance_types.length > 0 && (
            <p className="text-xs text-black/60 dark:text-white/60">Variance codes: {item.variance_types.join(", ")}</p>
          )}
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
