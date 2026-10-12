// Types mirror api/routes/agenda_items.py's AgendaItemOut / MeetingSummaryOut /
// CorrectionOut and api/routes/corrections.py's CorrectionIn exactly — see
// those files for the source of truth.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Board = "planning" | "zoning";
export type HvacTier = "A" | "B" | "C" | "D";
export type Sort = "score" | "date";

// Mirrors BUILDING_TYPES in ingestion/scoring.py.
export const BUILDING_TYPES = [
  "cannabis_cultivation",
  "climate_controlled_self_storage",
  "cold_storage",
  "data_center",
  "fences_decks_sheds_signs",
  "fitness",
  "hotel",
  "house_of_worship",
  "industrial_shell",
  "bulk_warehouse_distribution",
  "medical_lab",
  "mixed_use",
  "multifamily",
  "office",
  "parking_only",
  "parking_structure",
  "residential_1_3_family",
  "restaurant_commercial_kitchen",
  "retail",
  "school",
  "subdivision_no_building",
] as const;

export type DerivedField =
  | "building_type"
  | "stories"
  | "unit_count"
  | "square_footage"
  | "is_ground_up"
  | "involves_demolition"
  | "zone"
  | "variance_types";

export type FieldValue = string | number | boolean | string[] | null;

export interface Correction {
  raw: FieldValue;
  value: FieldValue;
  corrected_by: string | null;
  corrected_at: string | null;
}

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
  // Only the derived fields that carry a correction appear here.
  overrides: Partial<Record<DerivedField, Correction>>;
}

export interface AgendaItemFilters {
  town?: string;
  board?: Board;
  section?: string;
  dateFrom?: string;
  dateTo?: string;
  groundUp?: boolean;
  q?: string;
  tier?: HvacTier;
  // Omitted means the API default (best score first).
  sort?: Sort;
}

export function filtersToSearchParams(filters: AgendaItemFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.town) params.set("town", filters.town);
  if (filters.board) params.set("board", filters.board);
  if (filters.section) params.set("section", filters.section);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.groundUp) params.set("ground_up", "true");
  if (filters.q) params.set("q", filters.q);
  if (filters.tier) params.set("tier", filters.tier);
  if (filters.sort) params.set("sort", filters.sort);
  return params;
}

export async function fetchAgendaItems(filters: AgendaItemFilters): Promise<AgendaItem[]> {
  const response = await fetch(`${API_BASE_URL}/agenda-items?${filtersToSearchParams(filters).toString()}`);
  if (!response.ok) {
    throw new Error(`GET /agenda-items failed: ${response.status}`);
  }
  return response.json();
}

export interface CorrectionRequest {
  itemId: number;
  field: DerivedField;
  // null clears an existing correction.
  value: FieldValue;
  correctedBy: string;
}

export async function postCorrection({ itemId, field, value, correctedBy }: CorrectionRequest): Promise<AgendaItem> {
  const response = await fetch(`${API_BASE_URL}/agenda-items/${itemId}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value, corrected_by: correctedBy }),
  });
  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `POST correction failed: ${response.status}`);
  }
  return response.json();
}

export function meetingPdfUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
