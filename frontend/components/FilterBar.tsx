"use client";

import { useRef, useState } from "react";
import type { AgendaItemFilters, Board, HvacTier, Sort } from "@/lib/api";
import { countiesForState, statesList, townMeta, townsForCounty } from "@/lib/geography";

interface FilterBarProps {
  filters: AgendaItemFilters;
  sections: string[];
  onChange: (filters: AgendaItemFilters) => void;
}

const BOARDS: { value: Board; label: string }[] = [
  { value: "planning", label: "Planning" },
  { value: "zoning", label: "Zoning" },
];

const TIERS: HvacTier[] = ["A", "B", "C", "D"];

const SORTS: { value: Sort; label: string }[] = [
  { value: "score", label: "Best score first" },
  { value: "date", label: "Latest meeting first" },
];

const fieldClass =
  "rounded border border-black/15 bg-transparent px-2 py-1 text-sm dark:border-white/15";
const labelClass = "flex flex-col gap-1 text-xs";
const labelTextClass = "text-black/60 dark:text-white/60";

export function FilterBar({ filters, sections, onChange }: FilterBarProps) {
  // The search field needs its own local state: `filters.q` comes from the
  // URL (useSearchParams), and router.replace() is async, so wiring the
  // input straight to filters.q drops characters on fast typing — a
  // keystroke's onChange can fire before the previous one's URL update (and
  // resulting re-render) has landed, resetting the input mid-word.
  // Confirmed live. Debouncing the URL sync avoids a navigation per
  // keystroke too.
  const [searchValue, setSearchValue] = useState(filters.q ?? "");
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Follow the URL when it changes from elsewhere (back button, shared link).
  // Done while rendering rather than in an effect, so there's no extra render.
  const [lastSeenQ, setLastSeenQ] = useState(filters.q);
  if (filters.q !== lastSeenQ) {
    setLastSeenQ(filters.q);
    setSearchValue(filters.q ?? "");
  }

  function handleSearchChange(value: string) {
    setSearchValue(value);
    clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      onChange({ ...filters, q: value || undefined });
    }, 300);
  }

  // State/county are a pure UI drill-down toward picking a town — there's no
  // state/county column in the data, so only `filters.town` is a real
  // filter. Local state holds the in-progress selection (state chosen, county
  // not yet, say) that a persisted `filters.town` alone can't represent.
  const [selectedState, setSelectedState] = useState(() => townMeta(filters.town ?? "")?.state ?? "");
  const [selectedCounty, setSelectedCounty] = useState(() => townMeta(filters.town ?? "")?.county ?? "");

  const [lastSeenTown, setLastSeenTown] = useState(filters.town);
  if (filters.town !== lastSeenTown) {
    setLastSeenTown(filters.town);
    const meta = townMeta(filters.town ?? "");
    if (meta) {
      setSelectedState(meta.state);
      setSelectedCounty(meta.county);
    }
  }

  function handleStateChange(value: string) {
    setSelectedState(value);
    setSelectedCounty("");
    if (filters.town) onChange({ ...filters, town: undefined });
  }

  function handleCountyChange(value: string) {
    setSelectedCounty(value);
    if (filters.town) onChange({ ...filters, town: undefined });
  }

  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-black/10 px-4 py-3 dark:border-white/10">
      <label className={labelClass}>
        <span className={labelTextClass}>State</span>
        <select className={fieldClass} value={selectedState} onChange={(e) => handleStateChange(e.target.value)}>
          <option value="">All</option>
          {statesList().map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      {selectedState && (
        <label className={labelClass}>
          <span className={labelTextClass}>County</span>
          <select className={fieldClass} value={selectedCounty} onChange={(e) => handleCountyChange(e.target.value)}>
            <option value="">All</option>
            {countiesForState(selectedState).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      )}

      {selectedState && selectedCounty && (
        <label className={labelClass}>
          <span className={labelTextClass}>Town</span>
          <select
            className={fieldClass}
            value={filters.town ?? ""}
            onChange={(e) => onChange({ ...filters, town: e.target.value || undefined })}
          >
            <option value="">All</option>
            {townsForCounty(selectedState, selectedCounty).map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className={labelClass}>
        <span className={labelTextClass}>Board</span>
        <select
          className={fieldClass}
          value={filters.board ?? ""}
          onChange={(e) => onChange({ ...filters, board: (e.target.value || undefined) as Board | undefined })}
        >
          <option value="">All</option>
          {BOARDS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </label>

      <label className={labelClass}>
        <span className={labelTextClass}>Tier</span>
        <select
          className={fieldClass}
          value={filters.tier ?? ""}
          onChange={(e) => onChange({ ...filters, tier: (e.target.value || undefined) as HvacTier | undefined })}
        >
          <option value="">All</option>
          {TIERS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label className={labelClass}>
        <span className={labelTextClass}>Section</span>
        <select
          className={fieldClass}
          value={filters.section ?? ""}
          onChange={(e) => onChange({ ...filters, section: e.target.value || undefined })}
        >
          <option value="">All</option>
          {sections.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className={labelClass}>
        <span className={labelTextClass}>From</span>
        <input
          type="date"
          className={fieldClass}
          value={filters.dateFrom ?? ""}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value || undefined })}
        />
      </label>

      <label className={labelClass}>
        <span className={labelTextClass}>To</span>
        <input
          type="date"
          className={fieldClass}
          value={filters.dateTo ?? ""}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value || undefined })}
        />
      </label>

      <label className="flex items-center gap-2 pb-1.5 text-sm">
        <input
          type="checkbox"
          checked={filters.groundUp ?? false}
          onChange={(e) => onChange({ ...filters, groundUp: e.target.checked || undefined })}
        />
        Ground-up only
      </label>

      <label className={labelClass}>
        <span className={labelTextClass}>Sort</span>
        <select
          className={fieldClass}
          value={filters.sort ?? "score"}
          // "score" is the API default, so it stays out of the URL.
          onChange={(e) => onChange({ ...filters, sort: e.target.value === "date" ? "date" : undefined })}
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      <label className={`${labelClass} min-w-48 flex-1`}>
        <span className={labelTextClass}>Search</span>
        <input
          type="search"
          placeholder="project text or applicant…"
          className={fieldClass}
          value={searchValue}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </label>
    </div>
  );
}
