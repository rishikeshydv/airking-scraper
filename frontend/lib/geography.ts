// Static state/county metadata for the 5 in-scope towns (all Essex County,
// NJ today — see docs/PROD-SPEC.md). Not a general US geography reference:
// just enough to drive the State -> County -> Town cascading filter over
// towns that actually exist in this system. Add a row here when a new town
// is onboarded; don't anticipate towns beyond what's actually in scope.

export interface TownMeta {
  value: string;
  label: string;
  state: string;
  county: string;
}

export const TOWN_METADATA: TownMeta[] = [
  { value: "newark", label: "Newark", state: "New Jersey", county: "Essex" },
  { value: "bloomfield", label: "Bloomfield", state: "New Jersey", county: "Essex" },
  { value: "fairfield", label: "Fairfield", state: "New Jersey", county: "Essex" },
  { value: "livingston", label: "Livingston", state: "New Jersey", county: "Essex" },
  { value: "montclair", label: "Montclair", state: "New Jersey", county: "Essex" },
];

export function townMeta(value: string): TownMeta | undefined {
  return TOWN_METADATA.find((t) => t.value === value);
}

export function statesList(): string[] {
  return Array.from(new Set(TOWN_METADATA.map((t) => t.state))).sort();
}

export function countiesForState(state: string): string[] {
  return Array.from(new Set(TOWN_METADATA.filter((t) => t.state === state).map((t) => t.county))).sort();
}

export function townsForCounty(state: string, county: string): TownMeta[] {
  return TOWN_METADATA.filter((t) => t.state === state && t.county === county).sort((a, b) => a.label.localeCompare(b.label));
}
