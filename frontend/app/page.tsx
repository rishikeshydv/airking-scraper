import { Suspense } from "react";
import { TableView } from "@/components/TableView";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-black/10 px-4 py-3 dark:border-white/10">
        <h1 className="text-lg font-semibold">AirKing Data Tracker</h1>
        <p className="text-xs text-black/50 dark:text-white/50">
          Land-use leads across Newark, Bloomfield, Fairfield, Livingston, and Montclair
        </p>
      </header>
      <Suspense fallback={<p className="px-4 py-8 text-sm">Loading…</p>}>
        <TableView />
      </Suspense>
    </div>
  );
}
