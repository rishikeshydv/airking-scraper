"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { fetchAgendaItems, type AgendaItemFilters, type Board } from "@/lib/api";
import { AgendaTable } from "./AgendaTable";
import { FilterBar } from "./FilterBar";

function filtersFromSearchParams(params: URLSearchParams): AgendaItemFilters {
  return {
    town: params.get("town") || undefined,
    board: (params.get("board") as Board) || undefined,
    section: params.get("section") || undefined,
    dateFrom: params.get("date_from") || undefined,
    dateTo: params.get("date_to") || undefined,
    groundUp: params.get("ground_up") === "true" || undefined,
    q: params.get("q") || undefined,
  };
}

function filtersToSearchParams(filters: AgendaItemFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.town) params.set("town", filters.town);
  if (filters.board) params.set("board", filters.board);
  if (filters.section) params.set("section", filters.section);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.groundUp) params.set("ground_up", "true");
  if (filters.q) params.set("q", filters.q);
  return params;
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
