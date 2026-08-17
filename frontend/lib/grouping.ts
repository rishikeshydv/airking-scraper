import type { AgendaItem } from "./api";

export interface AgendaGroup {
  key: string;
  primary: AgendaItem;
  history: AgendaItem[];
}

/**
 * Groups repeat block/lot appearances (same project_id) into one row with
 * history, per docs/MILESTONES.md Milestone 6. Items with no project_id (no
 * block/lot to link on) each get their own single-item group. `items` must
 * already be sorted by meeting date desc (the API's default, latest first)
 * — group order then follows first-appearance order, i.e. each project's
 * own latest activity, and `primary` is that same latest occurrence (so the
 * collapsed row's displayed date always matches why the row is where it is).
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
    return { key, primary: history[0], history };
  });
}
