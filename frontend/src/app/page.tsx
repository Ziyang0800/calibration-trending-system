"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Search,
  FileDown,
  Layers,
  Zap,
  Radio,
  SlidersHorizontal,
  X,
  FileText,
  RotateCw,
} from "lucide-react";

// Types
interface Asset {
  id: number;
  serial: string;
  model: string | null;
  asset_number: string | null;
  nominal_ohms: number;
  source_sheet: string | null;
  set_id: string | null;
  category: string;
  unit: string;
  num_calibrations: number;
  last_cal_date: string | null;
  last_measured: number | null;
  status: "ok" | "out_of_trend" | "reviewed_out_of_trend" | "insufficient_data";
}

interface SetGroup {
  set_id: string;
  assets: Asset[];
  total: number;
  ok_count: number;
  out_count: number;
  insufficient_count: number;
}

interface DashboardData {
  sets: SetGroup[];
  total: number;
  ok_count: number;
  out_count: number;
  insufficient_count: number;
}

export default function Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [csrfToken, setCsrfToken] = useState("");
  useEffect(() => {
    fetch("/api/csrf", { credentials: "same-origin" })
      .then(response => response.ok ? response.json() : Promise.reject(new Error("Could not initialize form protection")))
      .then(result => setCsrfToken(result.csrf_token))
      .catch(() => setCsrfToken(""));
  }, []);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [setFilter, setSetFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  // Fetch Dashboard Data from Python Backend
  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error("Failed to load dashboard data");
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Could not connect to Python backend at 127.0.0.1:5000");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Flatten assets across all sets
  const allAssets = useMemo(() => {
    if (!data) return [];
    return data.sets.flatMap((s) => s.assets);
  }, [data]);

  // Compute live counts per category
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {
      all: allAssets.length,
      standard_resistor: 0,
      dcv_reference: 0,
      ac_divider: 0,
      waveform_generator: 0,
    };
    allAssets.forEach((a) => {
      const cat = a.category || "standard_resistor";
      if (counts[cat] !== undefined) counts[cat]++;
    });
    return counts;
  }, [allAssets]);

  // Filtered Assets
  const filteredAssets = useMemo(() => {
    return allAssets.filter((a) => {
      // Set filter
      if (setFilter !== "all" && a.set_id !== setFilter) return false;

      // Status filter
      if (statusFilter !== "all") {
        if (statusFilter === "out_of_trend") {
          if (a.status !== "out_of_trend" && a.status !== "reviewed_out_of_trend") return false;
        } else if (a.status !== statusFilter) {
          return false;
        }
      }

      // Category filter
      if (categoryFilter !== "all" && (a.category || "standard_resistor") !== categoryFilter) {
        return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const haystack = `${a.serial} ${a.model || ""} ${a.asset_number || ""} ${a.source_sheet || ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }

      return true;
    });
  }, [allAssets, setFilter, statusFilter, categoryFilter, searchQuery]);

  // Selection handlers
  const toggleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(filteredAssets.map((a) => a.id));
    } else {
      setSelectedIds([]);
    }
  };

  const toggleSelectOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  // Reset all filters
  const resetAllFilters = () => {
    setStatusFilter("all");
    setCategoryFilter("all");
    setSetFilter("all");
    setSearchQuery("");
  };

  // Format nominal readout
  const formatNominal = (a: Asset) => {
    if (a.category === "dcv_reference") return "10.0 V";
    if (a.category === "ac_divider") return a.model?.includes("10mV") ? "100:1 Ratio" : "10:1 Ratio";
    if (a.category === "waveform_generator") return "15 Points (dB)";
    const n = a.nominal_ohms;
    return n >= 1e6 ? `${n / 1e6} MΩ` : n >= 1e3 ? `${n / 1e3} kΩ` : `${n} Ω`;
  };

  // Format measured readout
  const formatMeasured = (a: Asset) => {
    if (a.last_measured === null || a.last_measured === undefined) return "—";
    if (a.category === "dcv_reference") return `${a.last_measured.toFixed(8)} V`;
    if (a.category === "ac_divider") return a.last_measured.toFixed(5);
    if (a.category === "waveform_generator") return `${a.last_measured > 0 ? "+" : ""}${a.last_measured.toFixed(4)} dB`;
    return a.last_measured.toFixed(7) + " Ω";
  };

  return (
    <div className="min-h-screen bg-[#f6f8fb] text-[#0b1329]">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-[#e2e8f0] px-7 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="w-3.5 h-3.5 bg-[#0a192f] rounded rotate-45 transform transition-transform hover:scale-110" />
          <h1 className="text-[15.5px] font-bold tracking-tight text-[#0a192f]">
            Calibration Trending
          </h1>
          <span className="text-[#94a3b8] text-xs font-light">/</span>
          <span className="text-xs font-semibold text-[#64748b] uppercase tracking-wider">
            Fleet Overview
          </span>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-[#e2e8f0] rounded-md text-[#334155] hover:bg-[#f8fafc] hover:text-[#0f172a] transition-all shadow-sm active:scale-95"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-blue-600" : ""}`} />
            Sync
          </button>
          <a
            href="/legacy/import"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-[#e2e8f0] rounded-md text-[#334155] hover:bg-[#f8fafc] hover:text-[#0f172a] transition-all shadow-sm"
          >
            <FileDown className="w-3.5 h-3.5 text-blue-600" />
            Import Cert
          </a>
          <Link href="/htbasic" className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold bg-[#0a192f] text-white rounded-md hover:bg-[#152744] transition-all shadow-sm">
  <FileText className="w-3.5 h-3.5 text-blue-400" />
  Cal. Factor Files
</Link>
        </div>
      </header>

      <main className="max-w-[1520px] mx-auto px-7 py-6">
        {/* Connection Error Banner */}
        {error && (
          <div className="mb-5 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between text-amber-900 text-sm">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span>{error}. Make sure <code>python MainApp.py</code> is running in PyCharm.</span>
            </div>
            <button onClick={fetchData} className="px-2.5 py-1 text-xs font-bold bg-amber-200 text-amber-950 rounded hover:bg-amber-300">
              Retry
            </button>
          </div>
        )}

        {/* Action Required Banner (Only if unreviewed out-of-trend exists) */}
        {data && data.out_count > 0 && (
          <div className="mb-5 p-3.5 bg-amber-50/90 border border-amber-300/80 rounded-xl flex items-center justify-between shadow-sm">
            <div className="flex items-center gap-2.5 text-amber-950 text-[13px] font-semibold">
              <span className="flex h-2 w-2 rounded-full bg-amber-500 animate-ping" />
              <span>Attention Required: {data.out_count} standard(s) outside 95% prediction interval awaiting metrologist review.</span>
            </div>
            <button
              onClick={() => setStatusFilter("out_of_trend")}
              className="px-3 py-1 bg-white border border-amber-300 text-amber-900 text-xs font-bold rounded-md hover:bg-amber-100 shadow-sm"
            >
              Isolate Alert(s)
            </button>
          </div>
        )}

        {/* Telemetry Metric KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {/* Card: Total */}
          <div
            onClick={() => setStatusFilter("all")}
            className={`p-4 bg-white rounded-xl border transition-all cursor-pointer shadow-sm relative overflow-hidden select-none hover:-translate-y-0.5 hover:shadow-md ${
              statusFilter === "all" ? "border-[#0a192f] ring-2 ring-[#0a192f]/10" : "border-[#e2e8f0]"
            }`}
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-[#0a192f]" />
            <div className="flex items-center justify-between mb-1 text-[#64748b]">
              <span className="text-xs font-semibold">Total Standards Tracked</span>
              <Activity className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-3xl font-extrabold tracking-tight font-mono text-[#0a192f]">
              {data ? data.total : "—"}
            </div>
          </div>

          {/* Card: Within Trend */}
          <div
            onClick={() => setStatusFilter("ok")}
            className={`p-4 bg-white rounded-xl border transition-all cursor-pointer shadow-sm relative overflow-hidden select-none hover:-translate-y-0.5 hover:shadow-md ${
              statusFilter === "ok" ? "border-emerald-600 ring-2 ring-emerald-600/10" : "border-[#e2e8f0]"
            }`}
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-emerald-600" />
            <div className="flex items-center justify-between mb-1 text-[#64748b]">
              <span className="text-xs font-semibold">Within Trend</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="text-3xl font-extrabold tracking-tight font-mono text-emerald-600">
              {data ? data.ok_count : "—"}
            </div>
          </div>

          {/* Card: Out of Trend */}
          <div
            onClick={() => setStatusFilter("out_of_trend")}
            className={`p-4 bg-white rounded-xl border transition-all cursor-pointer shadow-sm relative overflow-hidden select-none hover:-translate-y-0.5 hover:shadow-md ${
              statusFilter === "out_of_trend" ? "border-amber-600 ring-2 ring-amber-600/10" : "border-[#e2e8f0]"
            }`}
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-amber-600" />
            <div className="flex items-center justify-between mb-1 text-[#64748b]">
              <span className="text-xs font-semibold">Out of Trend (Unreviewed)</span>
              <AlertTriangle className="w-4 h-4 text-amber-600" />
            </div>
            <div className="text-3xl font-extrabold tracking-tight font-mono text-amber-600">
              {data ? data.out_count : "—"}
            </div>
          </div>

          {/* Card: Insufficient History */}
          <div
            onClick={() => setStatusFilter("insufficient_data")}
            className={`p-4 bg-white rounded-xl border transition-all cursor-pointer shadow-sm relative overflow-hidden select-none hover:-translate-y-0.5 hover:shadow-md ${
              statusFilter === "insufficient_data" ? "border-slate-500 ring-2 ring-slate-500/10" : "border-[#e2e8f0]"
            }`}
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-slate-400" />
            <div className="flex items-center justify-between mb-1 text-[#64748b]">
              <span className="text-xs font-semibold">Insufficient History</span>
              <Clock className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-3xl font-extrabold tracking-tight font-mono text-slate-600">
              {data ? data.insufficient_count : "—"}
            </div>
          </div>
        </div>

        {/* Hardware Track Category Segmented Controller */}
        <div className="bg-[#eef2f6] p-1 rounded-xl flex items-center gap-1 mb-4 border border-[#e2e8f0]">
          <button
            onClick={() => setCategoryFilter("all")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-[12.5px] font-semibold transition-all select-none ${
              categoryFilter === "all"
                ? "bg-white text-[#0a192f] shadow-sm font-bold"
                : "text-[#64748b] hover:text-[#0b1329] hover:bg-white/50"
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-blue-600" />
            <span>All Standards</span>
            <span className="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {categoryCounts.all}
            </span>
          </button>

          <button
            onClick={() => setCategoryFilter("standard_resistor")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-[12.5px] font-semibold transition-all select-none ${
              categoryFilter === "standard_resistor"
                ? "bg-white text-[#0a192f] shadow-sm font-bold"
                : "text-[#64748b] hover:text-[#0b1329] hover:bg-white/50"
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-emerald-600" />
            <span>Resistors</span>
            <span className="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {categoryCounts.standard_resistor}
            </span>
          </button>

          <button
            onClick={() => setCategoryFilter("dcv_reference")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-[12.5px] font-semibold transition-all select-none ${
              categoryFilter === "dcv_reference"
                ? "bg-white text-[#0a192f] shadow-sm font-bold"
                : "text-[#64748b] hover:text-[#0b1329] hover:bg-white/50"
            }`}
          >
            <Zap className="w-3.5 h-3.5 text-amber-500" />
            <span>DC Voltage Reference</span>
            <span className="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {categoryCounts.dcv_reference}
            </span>
          </button>

          <button
            onClick={() => setCategoryFilter("ac_divider")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-[12.5px] font-semibold transition-all select-none ${
              categoryFilter === "ac_divider"
                ? "bg-white text-[#0a192f] shadow-sm font-bold"
                : "text-[#64748b] hover:text-[#0b1329] hover:bg-white/50"
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-purple-600" />
            <span>AC Dividers</span>
            <span className="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {categoryCounts.ac_divider}
            </span>
          </button>

          <button
            onClick={() => setCategoryFilter("waveform_generator")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-[12.5px] font-semibold transition-all select-none ${
              categoryFilter === "waveform_generator"
                ? "bg-white text-[#0a192f] shadow-sm font-bold"
                : "text-[#64748b] hover:text-[#0b1329] hover:bg-white/50"
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-indigo-600" />
            <span>Waveform Generators</span>
            <span className="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {categoryCounts.waveform_generator}
            </span>
          </button>
        </div>

        {/* Secondary Toolbar: Set Filter Pills + Live Search */}
        <div className="bg-white p-3 rounded-xl border border-[#e2e8f0] flex items-center justify-between gap-4 mb-5 shadow-sm flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-[#64748b] mr-1">Set Filter:</span>
            {["all", "Set 1", "Set 2", "Set 3"].map((sName) => (
              <button
                key={sName}
                onClick={() => setSetFilter(sName)}
                className={`px-3 py-1 text-xs font-semibold rounded-full border transition-all ${
                  setFilter === sName
                    ? "bg-[#0a192f] text-white border-[#0a192f]"
                    : "bg-white text-[#475569] border-[#e2e8f0] hover:bg-slate-50"
                }`}
              >
                {sName === "all" ? "All Sets" : sName}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-[320px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter serial, model, trace ID..."
              className="w-full pl-9 pr-8 py-1.5 text-xs bg-[#f8fafc] border border-[#e2e8f0] rounded-md focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Master Fleet Table */}
        <div className="bg-white rounded-xl border border-[#e2e8f0] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#f8fafc] border-b border-[#e2e8f0] text-[11px] font-bold text-[#64748b] uppercase tracking-wider">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.length > 0 && selectedIds.length === filteredAssets.length}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                  </th>
                  <th className="px-4 py-3">Serial</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Equipment ID</th>
                  <th className="px-4 py-3 text-right">Nominal / Function</th>
                  <th className="px-4 py-3 text-center">Set</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3 text-right"># Cals</th>
                  <th className="px-4 py-3">Last Cal</th>
                  <th className="px-4 py-3 text-right">Last Measured</th>
                  <th className="px-4 py-3 text-center">Trend Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f1f5f9] text-[13px]">
                {filteredAssets.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="py-12 text-center text-slate-400 text-xs">
                      No standards match the current filter selection.
                      <button onClick={resetAllFilters} className="ml-2 font-bold text-blue-600 hover:underline">
                        Reset filters
                      </button>
                    </td>
                  </tr>
                ) : (
                  filteredAssets.map((asset) => {
                    const isSelected = selectedIds.includes(asset.id);
                    const isOut = asset.status === "out_of_trend";
                    const isRev = asset.status === "reviewed_out_of_trend";

                    return (
                      <tr
                        key={asset.id}
                        className={`transition-colors hover:bg-slate-50/80 cursor-pointer ${
                          isOut ? "bg-amber-50/40 border-l-[3px] border-l-amber-500" : isRev ? "bg-blue-50/40 border-l-[3px] border-l-blue-600" : ""
                        }`}
                        onClick={(e) => {
                          if ((e.target as HTMLElement).tagName !== "INPUT") {
window.location.href = `/assets/${asset.id}`;                          }
                        }}
                      >
                        <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectOne(asset.id)}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                          />
                        </td>
                        <td className="px-4 py-2.5 font-mono font-bold text-blue-700 hover:underline">
                          <Link href={`/assets/${asset.id}`}>{asset.serial}</Link>                        </td>
                        <td className="px-4 py-2.5 font-semibold text-[#1e293b]">{asset.model || "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-slate-500">{asset.asset_number || "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-right font-medium">{formatNominal(asset)}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className="inline-block px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                            {asset.set_id || "—"}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 text-xs">
                          {asset.category === "dcv_reference"
                            ? "DC Voltage Ref"
                            : asset.category === "ac_divider"
                            ? "AC Voltage Divider"
                            : asset.category === "waveform_generator"
                            ? "Waveform Gen"
                            : asset.source_sheet || "Resistor Decade"}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-right text-slate-600">{asset.num_calibrations}</td>
                        <td className="px-4 py-2.5 font-mono text-slate-600">{asset.last_cal_date || "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-right font-semibold text-[#0a192f]">
                          {formatMeasured(asset)}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {asset.status === "ok" ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                              In Trend
                            </span>
                          ) : asset.status === "reviewed_out_of_trend" ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                              Reviewed
                            </span>
                          ) : asset.status === "out_of_trend" ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-300">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                              Out of Trend
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                              Insufficient
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Spring Floating Batch Action Drawer */}
        <div
          className={`fixed bottom-6 left-1/2 -translate-x-1/2 bg-[#0a192f] text-white px-5 py-2.5 rounded-full shadow-2xl flex items-center gap-4 transition-all duration-300 z-50 ${
            selectedIds.length > 0 ? "translate-y-0 opacity-100" : "translate-y-24 opacity-0 pointer-events-none"
          }`}
        >
          <span className="text-xs font-medium">
            <strong className="font-mono">{selectedIds.length}</strong> standards selected
          </span>
          <form method="post" action="/legacy/report/generate" target="_blank">
            <input type="hidden" name="csrf_token" value={csrfToken} />
            {selectedIds.map((id) => (
              <input key={id} type="hidden" name="asset_ids" value={id} />
            ))}
            <button
              type="submit"
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-full transition-all"
            >
              Generate PDF Report
            </button>
          </form>
          <button
            onClick={() => setSelectedIds([])}
            className="text-xs text-slate-400 hover:text-white transition-colors"
          >
            Clear
          </button>
        </div>
      </main>
    </div>
  );
}