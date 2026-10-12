import type { DerivedField, FieldValue } from "./api";

// How each correctable field is edited and how its text input becomes the
// value POSTed to /agenda-items/{id}/corrections.
export type FieldKind = "building_type" | "integer" | "yes_no" | "text" | "codes";

export const CORRECTABLE_FIELDS: { field: DerivedField; label: string; kind: FieldKind }[] = [
  { field: "building_type", label: "Building type", kind: "building_type" },
  { field: "stories", label: "Stories", kind: "integer" },
  { field: "unit_count", label: "Units", kind: "integer" },
  { field: "square_footage", label: "Square footage", kind: "integer" },
  { field: "is_ground_up", label: "Ground-up", kind: "yes_no" },
  { field: "involves_demolition", label: "Demolition", kind: "yes_no" },
  { field: "zone", label: "Zone", kind: "text" },
  { field: "variance_types", label: "Variance codes", kind: "codes" },
];

export function formatFieldValue(value: FieldValue): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "none";
  return String(value);
}

/** Text from the edit input → the value to send, or an error message when it doesn't fit the field. */
export function parseFieldInput(kind: FieldKind, text: string): { value: FieldValue } | { error: string } {
  const trimmed = text.trim();

  if (kind === "integer") {
    if (!/^\d+$/.test(trimmed)) return { error: "Enter a whole number" };
    return { value: Number(trimmed) };
  }
  if (kind === "yes_no") {
    if (trimmed !== "yes" && trimmed !== "no") return { error: "Choose Yes or No" };
    return { value: trimmed === "yes" };
  }
  if (kind === "codes") {
    const codes = trimmed
      .split(",")
      .map((code) => code.trim().toLowerCase())
      .filter((code) => code !== "");
    return { value: codes };
  }
  if (trimmed === "") return { error: "Enter a value" };
  return { value: trimmed };
}

/** The current value as the text the edit input starts with. */
export function fieldInputText(kind: FieldKind, value: FieldValue): string {
  if (value === null) return "";
  if (kind === "yes_no") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}
