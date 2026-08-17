"use client";

import { Fragment, useState } from "react";
import type { AgendaItem } from "@/lib/api";
import { meetingPdfUrl } from "@/lib/api";
import { groupByProject } from "@/lib/grouping";
import { RowDetail } from "./RowDetail";

const linkClass = "text-blue-600 underline dark:text-blue-400";
const cellClass = "px-2 py-1.5";
const headerCellClass = "px-2 py-2";

export function AgendaTable({ items }: { items: AgendaItem[] }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const groups = groupByProject(items);

  if (groups.length === 0) {
    return <p className="px-4 py-8 text-sm text-black/60 dark:text-white/60">No agenda items match these filters.</p>;
  }

  return (
    <table className="w-full min-w-[900px] border-collapse text-sm">
      <thead>
        <tr className="border-b border-black/10 text-left text-xs tracking-wide text-black/50 uppercase dark:border-white/10 dark:text-white/50">
          <th className={headerCellClass}>Score</th>
          <th className={headerCellClass}>Tier</th>
          <th className={headerCellClass}>Town / Board</th>
          <th className={headerCellClass}>Date</th>
          <th className={headerCellClass}>Section</th>
          <th className={headerCellClass}>Applicant</th>
          <th className={headerCellClass}>Premises</th>
          <th className={headerCellClass}>Block / Lot</th>
          <th className={headerCellClass}>Building Type</th>
          <th className={headerCellClass}>Ground-up</th>
          <th className={headerCellClass}>Links</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((group) => {
          const item = group.primary;
          const isExpanded = expandedKey === group.key;
          return (
            <Fragment key={group.key}>
              <tr
                onClick={() => setExpandedKey(isExpanded ? null : group.key)}
                className="cursor-pointer border-b border-black/5 hover:bg-black/[.03] dark:border-white/5 dark:hover:bg-white/[.04]"
              >
                <td className={`${cellClass} font-mono`}>{item.hvac_score ?? "—"}</td>
                <td className={cellClass}>{item.hvac_tier ?? "—"}</td>
                <td className={`${cellClass} capitalize`}>
                  {item.meeting.town} / {item.meeting.board}
                </td>
                <td className={cellClass}>{item.meeting.meeting_date}</td>
                <td className={cellClass}>{item.agenda_section ?? "—"}</td>
                <td className={cellClass}>{item.applicant || "—"}</td>
                <td className={cellClass}>{item.premises || "—"}</td>
                <td className={cellClass}>
                  {item.block ? `${item.block}${item.lots.length ? "/" + item.lots.join(",") : ""}` : "—"}
                  {group.history.length > 1 && (
                    <span className="ml-1 text-xs text-black/40 dark:text-white/40">({group.history.length}x)</span>
                  )}
                </td>
                <td className={cellClass}>{item.building_type ?? "—"}</td>
                <td className={cellClass}>{item.is_ground_up === null ? "—" : item.is_ground_up ? "Yes" : "No"}</td>
                <td className={cellClass} onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-3">
                    {item.meeting.source_pdf_url ? (
                      <a className={linkClass} href={meetingPdfUrl(item.meeting.source_pdf_url)} target="_blank" rel="noopener noreferrer">
                        PDF
                      </a>
                    ) : (
                      <span className="text-black/30 dark:text-white/30">PDF</span>
                    )}
                    {item.meeting.google_drive_url ? (
                      <a className={linkClass} href={item.meeting.google_drive_url} target="_blank" rel="noopener noreferrer">
                        Drive
                      </a>
                    ) : (
                      <span className="text-black/30 dark:text-white/30">Drive</span>
                    )}
                  </div>
                </td>
              </tr>
              {isExpanded && (
                <tr>
                  <td colSpan={11} className="border-b border-black/5 bg-black/[.02] px-4 py-3 dark:border-white/5 dark:bg-white/[.03]">
                    <RowDetail group={group} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
