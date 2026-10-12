"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import {
  fetchAgendaItems,
  filtersToSearchParams,
  type AgendaItemFilters,
  type Board,
  type HvacTier,
  type Sort,
} from "@/lib/api";
import { AgendaTable } from "./AgendaTable";
import { FilterBar } from "./FilterBar";

const BOARDS: readonly Board[] = ["planning", "zoning"];
const TIERS: readonly HvacTier[] = ["A", "B", "C", "D"];
const SORTS: readonly Sort[] = ["score", "date"];

/** The URL value when it is one of the allowed values, otherwise undefined (a hand-edited URL can't inject others). */
function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((candidate) => candidate === value);
}

function filtersFromSearchParams(params: URLSearchParams): AgendaItemFilters {
  return {
    town: params.get("town") || undefined,
    board: oneOf(params.get("board"), BOARDS),
    section: params.get("section") || undefined,
    dateFrom: params.get("date_from") || undefined,
    dateTo: params.get("date_to") || undefined,
    groundUp: params.get("ground_up") === "true" || undefined,
    q: params.get("q") || undefined,
    tier: oneOf(params.get("tier"), TIERS),
    sort: oneOf(params.get("sort"), SORTS),
  };
}

export function TableView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);

  const itemsQuery = useQuery({
    queryKey: ["agenda-items", filters],
    queryFn: () => fetchAgendaItems(filters),
  });

  // Unfiltered, so the section dropdown always shows every section that
  // exists in the data — not just the ones surviving the current filters.
  const allItemsQuery = useQuery({
    queryKey: ["agenda-items", "unfiltered"],
    queryFn: () => fetchAgendaItems({}),
    staleTime: 5 * 60 * 1000,
  });

  const sections = useMemo(() => {
    const values = new Set<string>();
    for (const item of allItemsQuery.data ?? []) {
      if (item.agenda_section) values.add(item.agenda_section);
    }
    return Array.from(values).sort();
  }, [allItemsQuery.data]);

  function handleFilterChange(next: AgendaItemFilters) {
    router.replace(`${pathname}?${filtersToSearchParams(next).toString()}`, { scroll: false });
  }

  return (
    <div className="flex flex-1 flex-col">
      <FilterBar filters={filters} sections={sections} onChange={handleFilterChange} />
      <main className="flex-1 overflow-auto">
        {itemsQuery.isLoading && <p className="px-4 py-8 text-sm">Loading…</p>}
        {itemsQuery.isError && (
          <p className="px-4 py-8 text-sm text-red-600 dark:text-red-400">Failed to load agenda items. Is the API running?</p>
        )}
        {itemsQuery.data && <AgendaTable items={itemsQuery.data} />}
      </main>
    </div>
  );
}
