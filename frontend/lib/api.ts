// Types mirror api/routes/agenda_items.py's AgendaItemOut / MeetingSummaryOut
// exactly — see that file for the source of truth.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Board = "planning" | "zoning";
export type HvacTier = "A" | "B" | "C" | "D";

export interface MeetingSummary {
  id: number;
  town: string;
  board: Board;
  meeting_date: string;
  meeting_type: string | null;
  google_drive_url: string | null;
  source_pdf_url: string | null;
}

export interface AgendaItem {
  id: number;
  meeting: MeetingSummary;
  project_id: number | null;
  agenda_section: string | null;
  item_number: number;
  application_id: string;
  premises: string;
  block: string;
  lots: string[];
  ward: string;
  applicant: string;
  attorney: string | null;
  project_text: string;
  variances_raw: string | null;
  building_type: string | null;
  stories: number | null;
  unit_count: number | null;
  square_footage: number | null;
  is_ground_up: boolean | null;
  involves_demolition: boolean | null;
  zone: string | null;
  variance_types: string[];
  extraction_confidence: number | null;
  hvac_tier: HvacTier | null;
  hvac_score: number | null;
}

export interface AgendaItemFilters {
  town?: string;
  board?: Board;
  section?: string;
  dateFrom?: string;
  dateTo?: string;
  groundUp?: boolean;
  q?: string;
}

export async function fetchAgendaItems(filters: AgendaItemFilters): Promise<AgendaItem[]> {
  const params = new URLSearchParams();
  if (filters.town) params.set("town", filters.town);
  if (filters.board) params.set("board", filters.board);
  if (filters.section) params.set("section", filters.section);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.groundUp) params.set("ground_up", "true");
  if (filters.q) params.set("q", filters.q);

  const response = await fetch(`${API_BASE_URL}/agenda-items?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`GET /agenda-items failed: ${response.status}`);
  }
  return response.json();
}

export function meetingPdfUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
