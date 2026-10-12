import type { AgendaItem } from "./api";

export interface AgendaGroup {
  key: string;
  primary: AgendaItem;
  history: AgendaItem[];
}

/**
 * Groups repeat block/lot appearances (same project_id) into one row with
 * history, per docs/MILESTONES.md Milestone 6. Items with no project_id (no
 * block/lot to link on) each get their own single-item group. Group order
 * follows the API's order (best score first by default, or latest meeting
 * first), and `primary` is the occurrence that appeared first in that order
 * — so the collapsed row's displayed score/date always match why the row is
 * where it is. `history` lists every occurrence, latest meeting first.
 */
export function groupByProject(items: AgendaItem[]): AgendaGroup[] {
  const groups = new Map<string, AgendaItem[]>();

  for (const item of items) {
    const key = item.project_id !== null ? `project:${item.project_id}` : `item:${item.id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.push(item);
    } else {
      groups.set(key, [item]);
    }
  }

  return Array.from(groups.entries()).map(([key, group]) => {
    const history = [...group].sort((a, b) => b.meeting.meeting_date.localeCompare(a.meeting.meeting_date));
    return { key, primary: group[0], history };
  });
}
