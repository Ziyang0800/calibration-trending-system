"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  FileSpreadsheet,
  Edit3,
  Copy,
  Check,
  Zap,
  Activity,
  Radio,
  SlidersHorizontal,
  X,
  FileText,
  Clock,
  AlertTriangle,
  RotateCw,
} from "lucide-react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  Line,
  ComposedChart,
  Area,
} from "recharts";

interface Calibration {
  id: number;
  date: string;
  measured_value: number;
  mu_relative: number;
  source: string;
  cert_number: string | null;
  reviewer_comment: string | null;
  excluded_from_regression: boolean;
  reviewer_attachment_path: string | null;
  pressure_hpa: number | null;
  is_adjusted: boolean;
  location: string | null;
  accumulated_days: number;
  error_ppm?: number;
  drift_ppm?: number;
  predicted?: number | null;
  lower?: number | null;
  upper?: number | null;
  out_of_trend: boolean;
  display_status: string;
}

interface TestPoint {
  id: number;
  point_name: string;
  group_name: string;
  nominal_value: number;
  unit: string;
  display_order: number;
  latest_value: number | null;
  latest_date: string | null;
  drift: number | null;
  status: string;
}

interface AssetDetailData {
  asset: {
    id: number;
    serial: string;
    model: string;
    asset_number: string | null;
    nominal_ohms: number;
    source_sheet: string | null;
    source_workbook: string | null;
    set_id: string | null;
    category: string;
    unit: string;
  };
  calibrations: Calibration[];
  trend: {
    n: number;
    slope: number;
    Syx: number;
    latest_adj_idx: number;
  } | null;
  stability: {
    spec_description: string;
    elapsed_days: number;
    observed_drift_ppm: number;
    allowance_ppm: number;
    exceeds: boolean;
  } | null;
  test_points: TestPoint[];
  active_test_point: TestPoint | null;
  active_test_point_id: number | null;
}

export default function AssetDetailPage() {
  const params = useParams();
  const assetId = params?.id;

  const [data, setData] = useState<AssetDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTpId, setActiveTpId] = useState<number | null>(null);

  // Chart Mode: 'primary' (Ohms/V/dB) vs 'relative' (ppm/deviation)
  const [chartMode, setChartMode] = useState<"primary" | "relative">("primary");

  // Note Modal
  const [activeNote, setActiveNote] = useState<{
    date: string;
    comment: string;
    attachPath: string | null;
    calId: number;
  } | null>(null);

  // Copied chip state
  const [copied, setCopied] = useState(false);

  const fetchDetail = async (tpId?: number | null) => {
    try {
      setLoading(true);
      const url = tpId
        ? `/api/assets/${assetId}?tp=${tpId}`
        : `/api/assets/${assetId}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to load asset details");
      const json: AssetDetailData = await res.json();
      setData(json);
      setActiveTpId(json.active_test_point_id);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Could not connect to Python backend");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (assetId) fetchDetail();
  }, [assetId]);

  const copySerial = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Prepare chart series data
  const chartData = useMemo(() => {
    if (!data || !data.calibrations) return [];
    const isPrimary = chartMode === "primary";

    return data.calibrations.map((c) => {
      const x = c.accumulated_days;
      const y = isPrimary ? c.measured_value : c.error_ppm ?? null;
      const pred = isPrimary ? c.predicted : (c.predicted ? c.error_ppm : null);
      const low = isPrimary ? c.lower : null;
      const up = isPrimary ? c.upper : null;

      return {
        x,
        date: c.date,
        measured: y,
        predicted: pred,
        lower: low,
        upper: up,
        status: c.display_status,
        is_adjusted: c.is_adjusted,
        pressure: c.pressure_hpa,
        location: c.location,
      };
    });
  }, [data, chartMode]);

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-[#f6f8fb] flex items-center justify-center">
        <div className="flex items-center gap-2 text-slate-500 text-sm font-semibold">
          <RotateCw className="w-4 h-4 animate-spin text-blue-600" />
          Loading standard telemetry...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#f6f8fb] p-8 flex items-center justify-center">
        <div className="bg-white p-6 rounded-xl border border-red-200 shadow-sm max-w-md text-center">
          <AlertTriangle className="w-8 h-8 text-red-500 mx-auto mb-3" />
          <h3 className="text-base font-bold text-red-950 mb-1">Standard Not Found</h3>
          <p className="text-xs text-slate-600 mb-4">{error || "Asset ID does not exist in database."}</p>
          <Link href="/" className="px-4 py-2 bg-[#0a192f] text-white rounded-md text-xs font-bold">
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const { asset, calibrations, trend, stability, test_points, active_test_point } = data;

  return (
    <div className="min-h-screen bg-[#f6f8fb] text-[#0b1329] pb-16">
      {/* Top Header */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-[#e2e8f0] px-7 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#64748b] hover:text-[#0b1329] transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" />
            Dashboard
          </Link>
          <span className="text-[#94a3b8] text-xs font-light">/</span>
          <span className="text-xs font-semibold text-[#64748b]">{asset.set_id || "Unassigned"}</span>
          <span className="text-[#94a3b8] text-xs font-light">/</span>
          <span className="text-xs font-bold text-[#0a192f]">{asset.model || asset.serial}</span>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={`/legacy/export/asset/${asset.id}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-[#e2e8f0] rounded-md text-[#334155] hover:bg-[#f8fafc] shadow-sm"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
            Export Excel
          </a>
          <a
            href={`/legacy/assets/${asset.id}/edit`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-[#0a192f] text-white rounded-md hover:bg-[#152744] shadow-sm"
          >
            <Edit3 className="w-3.5 h-3.5 text-blue-400" />
            Edit Asset
          </a>
        </div>
      </header>

      <main className="max-w-[1520px] mx-auto px-7 py-6">
        {/* Command Hero Banner */}
        <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm flex items-center justify-between mb-6 flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-blue-50 text-blue-600 border border-blue-200 flex items-center justify-center shrink-0">
              {asset.category === "waveform_generator" ? (
                <Activity className="w-6 h-6" />
              ) : asset.category === "dcv_reference" ? (
                <Zap className="w-6 h-6 text-amber-500" />
              ) : asset.category === "ac_divider" ? (
                <Radio className="w-6 h-6 text-purple-600" />
              ) : (
                <SlidersHorizontal className="w-6 h-6 text-emerald-600" />
              )}
            </div>

            <div>
              <h2 className="text-xl font-extrabold tracking-tight text-[#0a192f]">
                {asset.model || asset.serial}
              </h2>
              <div className="flex items-center gap-3 text-xs text-[#64748b] mt-1 flex-wrap">
                <span>Equipment ID: <strong className="text-[#1e293b]">{asset.asset_number || "—"}</strong></span>
                <span>·</span>
                <span className="flex items-center gap-1.5">
                  Serial:
                  <button
                    onClick={() => copySerial(asset.serial)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded font-mono text-xs transition-colors"
                  >
                    <strong>{asset.serial}</strong>
                    {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3 text-slate-400" />}
                  </button>
                </span>
                <span>·</span>
                <span>Category: <strong className="text-[#1e293b]">{asset.category.replace("_", " ").toUpperCase()}</strong></span>
                <span>·</span>
                <span>Set: <strong className="text-[#1e293b]">{asset.set_id || "Unassigned"}</strong></span>
              </div>
            </div>
          </div>
        </div>

        {/* Multi-Point Characterization Matrix (If multiple points exist) */}
        {test_points && test_points.length > 1 && (
          <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm mb-6">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
              <h3 className="text-sm font-bold text-[#0a192f] flex items-center gap-2">
                <Radio className="w-4 h-4 text-blue-600" />
                Characterized Test Points Matrix ({test_points.length} Series)
              </h3>
              <span className="text-xs text-slate-400">Click any row to switch active curve below</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-[12.5px]">
                <thead>
                  <tr className="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                    <th className="py-2.5 px-3">Test Point</th>
                    <th className="py-2.5 px-3">Classification</th>
                    <th className="py-2.5 px-3 text-right">Latest Calibrated Value</th>
                    <th className="py-2.5 px-3 text-right">Drift Since Prior Cal</th>
                    <th className="py-2.5 px-3">Latest Cal Date</th>
                    <th className="py-2.5 px-3 text-center">Trend Status</th>
                    <th className="py-2.5 px-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {test_points.map((tp) => {
                    const isActive = tp.id === activeTpId;
                    return (
                      <tr
                        key={tp.id}
                        onClick={() => fetchDetail(tp.id)}
                        className={`transition-colors cursor-pointer hover:bg-slate-50/80 ${
                          isActive ? "bg-blue-50/70 border-l-[3px] border-l-blue-600 font-semibold" : ""
                        }`}
                      >
                        <td className="py-2 px-3 text-blue-700">{tp.point_name}</td>
                        <td className="py-2 px-3 text-slate-500 text-xs">{tp.group_name}</td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-[#0a192f]">
                          {tp.latest_value !== null ? `${tp.latest_value.toFixed(5)} ${tp.unit}` : "—"}
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-slate-700">
                          {tp.drift !== null ? `${tp.drift > 0 ? "+" : ""}${tp.drift.toFixed(4)}` : "—"}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-600 text-xs">{tp.latest_date || "—"}</td>
                        <td className="py-2 px-3 text-center">
                          {tp.status === "ok" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              In Trend
                            </span>
                          ) : tp.status === "reviewed_out_of_trend" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                              Reviewed
                            </span>
                          ) : tp.status === "out_of_trend" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-300">
                              Out of Trend
                            </span>
                          ) : (
                            <span className="text-slate-400 text-xs">Baseline</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-center">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              fetchDetail(tp.id);
                            }}
                            className={`px-2.5 py-0.5 rounded text-[11px] font-bold transition-all ${
                              isActive ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                            }`}
                          >
                            {isActive ? "Active" : "View"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 2-Column Info & Specs Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
          {/* Card: Active Series Specification */}
          <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
              <h3 className="text-sm font-bold text-[#0a192f]">Active Characterization Series</h3>
              <span className="px-2 py-0.5 text-xs font-bold rounded bg-slate-100 text-slate-700">
                {active_test_point ? active_test_point.point_name : `${asset.nominal_ohms} Ω Nominal`}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-y-2.5 text-xs">
              <span className="text-slate-500">Classification:</span>
              <span className="font-semibold text-slate-800">{active_test_point?.group_name || asset.source_sheet}</span>

              <span className="text-slate-500">Calibration Events:</span>
              <span className="font-semibold text-slate-800">{calibrations.length} records</span>

              {trend && (
                <>
                  <span className="text-slate-500">Regression Fit:</span>
                  <span className="font-semibold text-slate-800">
                    n = {trend.n}{" "}
                    {trend.latest_adj_idx !== -1 ? (
                      <span className="text-amber-600">(post-adjustment epoch)</span>
                    ) : (
                      <span className="text-slate-400">(excludes latest cal)</span>
                    )}
                  </span>

                  <span className="text-slate-500">Annual Drift Rate:</span>
                  <span className="font-mono font-bold text-blue-700">
                    {(trend.slope * 365.25).toExponential(3)} {asset.unit}/year
                  </span>

                  <span className="text-slate-500">Residual Error (Syx):</span>
                  <span className="font-mono text-slate-700">{trend.Syx.toExponential(3)}</span>
                </>
              )}
            </div>
          </div>

          {/* Card: Stability Check / Pressure Context */}
          {stability ? (
            <div className={`bg-white p-5 rounded-xl border shadow-sm ${stability.exceeds ? "border-amber-300" : "border-[#e2e8f0]"}`}>
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                <h3 className="text-sm font-bold text-[#0a192f]">Manufacturer Stability Check</h3>
                <span className={`px-2 py-0.5 text-xs font-bold rounded ${stability.exceeds ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                  {stability.exceeds ? "Exceeds Spec" : "Within Spec"}
                </span>
              </div>

              <div className="text-xs space-y-2">
                <div className="text-slate-500">Spec: <strong className="text-slate-800">{stability.spec_description}</strong></div>
                <div className="text-slate-500">
                  Observed drift across <strong>{stability.elapsed_days} days</strong>:{" "}
                  <strong className={stability.exceeds ? "text-amber-700 font-mono" : "text-emerald-700 font-mono"}>
                    {stability.observed_drift_ppm > 0 ? "+" : ""}{stability.observed_drift_ppm.toFixed(2)} ppm
                  </strong>{" "}
                  (Limit: ±{stability.allowance_ppm.toFixed(2)} ppm)
                </div>

                {/* Bar Gauge */}
                <div className="pt-2">
                  <div className="h-2.5 bg-slate-100 rounded-full relative overflow-visible">
                    <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-slate-300 -translate-x-1/2" />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 rounded-full border-2 border-white shadow-sm"
                      style={{
                        left: `${Math.min(98, Math.max(2, 50 + (stability.observed_drift_ppm / stability.allowance_ppm) * 50))}%`,
                        backgroundColor: stability.exceeds ? "#d97706" : "#059669",
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : asset.category === "dcv_reference" ? (
            <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                <h3 className="text-sm font-bold text-[#0a192f]">Barometric Pressure Context</h3>
                <span className="px-2 py-0.5 text-xs font-bold rounded bg-slate-100 text-slate-700">Altitude Sensitivity</span>
              </div>
              <p className="text-xs text-slate-600 mb-3">
                Fluke 732A/C references exhibit mechanical barometric sensitivity (~ -2.5 to -3 nV/hPa). Elevation difference between Loveland (~845 hPa) and Roseville (~1013 hPa) creates step shifts.
              </p>
              {calibrations.length > 0 && calibrations[calibrations.length - 1].pressure_hpa && (
                <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs flex items-center justify-between font-mono">
                  <span>Latest Ambient: <strong>{calibrations[calibrations.length - 1].pressure_hpa} hPa</strong></span>
                  <span className="text-slate-500">{calibrations[calibrations.length - 1].location || "Roseville"}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm flex items-center justify-center text-center p-6 text-slate-500 text-xs">
              Continuous multi-year regression active across all historical observations.
            </div>
          )}
        </div>

        {/* Interactive Trend Curve Canvas */}
        <div className="bg-white p-5 rounded-xl border border-[#e2e8f0] shadow-sm mb-6">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4 flex-wrap gap-2">
            <h3 className="text-sm font-bold text-[#0a192f]">
              Regression Trend &amp; 95% Prediction Interval: {active_test_point?.point_name || asset.model}
            </h3>

            <div className="bg-slate-100 p-1 rounded-lg flex items-center gap-1 border border-slate-200">
              <button
                onClick={() => setChartMode("primary")}
                className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                  chartMode === "primary" ? "bg-white text-[#0a192f] shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Measured ({asset.unit})
              </button>
              <button
                onClick={() => setChartMode("relative")}
                className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                  chartMode === "relative" ? "bg-white text-[#0a192f] shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {asset.unit === "dB" ? "Deviation (dB)" : "Relative Error (ppm)"}
              </button>
            </div>
          </div>

          <div className="w-full h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="x" type="number" unit=" d" label={{ value: "Accumulated Days in Service", position: "bottom", offset: 0, fontSize: 11 }} />
                <YAxis
                  domain={["auto", "auto"]}
                  tickFormatter={(v) => (chartMode === "primary" ? v.toFixed(asset.unit === "V" ? 7 : asset.unit === "dB" ? 4 : 5) : v.toFixed(2))}
                  label={{
                    value: chartMode === "primary" ? `Measured (${asset.unit})` : "Drift (ppm)",
                    angle: -90,
                    position: "left",
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  formatter={(val: any) => [typeof val === "number" ? val.toFixed(asset.unit === "V" ? 8 : 5) : val, "Value"]}
                  labelFormatter={(xVal) => `Day ${xVal}`}
                />
                <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12 }} />

                {/* 95% Limits as clean line bounds */}
                {chartMode === "primary" && (
                  <>
                    <Line type="monotone" dataKey="upper" stroke="#93c5fd" strokeWidth={1.5} dot={false} name="95% Upper Limit" />
                    <Line type="monotone" dataKey="lower" stroke="#93c5fd" strokeWidth={1.5} dot={false} name="95% Lower Limit" />
                    <Line type="monotone" dataKey="predicted" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Prediction" />
                  </>
                )}

                {/* Measured Scatter Points */}
                <Scatter dataKey="measured" name="Measured Value" fill="#0a192f" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Calibration History Data Grid (Zero Horizontal Overflow) */}
        <div className="bg-white rounded-xl border border-[#e2e8f0] overflow-hidden shadow-sm">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-bold text-[#0a192f]">
              Calibration History: {active_test_point?.point_name || "Readings"}
            </h3>
            <span className="text-xs text-slate-400">{calibrations.length} total events</span>
          </div>

          <div className="max-h-[540px] overflow-y-auto">
            <table className="w-full text-left border-collapse text-[12.5px]">
              <thead className="sticky top-0 bg-slate-50 shadow-sm z-10 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="py-2.5 px-3">Cal Date</th>
                  <th className="py-2.5 px-3 text-right">Measured Value</th>
                  <th className="py-2.5 px-3 text-right">Uncertainty</th>
                  <th className="py-2.5 px-3 text-right">Error</th>
                  <th className="py-2.5 px-3 text-right">Drift</th>
                  <th className="py-2.5 px-3 text-center">95% Acceptance Limits</th>
                  {asset.category === "dcv_reference" && (
                    <>
                      <th className="py-2.5 px-3">Location</th>
                      <th className="py-2.5 px-3 text-right">Pressure</th>
                    </>
                  )}
                  <th className="py-2.5 px-3 text-center">Trend Status</th>
                  <th className="py-2.5 px-3 text-center">Note</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {calibrations.slice().reverse().map((c) => {
                  const isOut = c.display_status === "out_of_trend";
                  const isRev = c.display_status === "reviewed_out_of_trend";

                  return (
                    <tr
                      key={c.id}
                      className={`hover:bg-slate-50/80 transition-colors ${
                        isOut ? "bg-amber-50/40 border-l-[3px] border-l-amber-500" : isRev ? "bg-blue-50/40 border-l-[3px] border-l-blue-600" : ""
                      }`}
                    >
                      <td className="py-2 px-3 font-mono font-bold text-[#1e293b]">
                        {c.date}
                        {c.is_adjusted && (
                          <span className="ml-1.5 px-1 py-0.2 rounded text-[10px] font-bold bg-amber-100 text-amber-800">
                            Adj
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-right font-mono font-bold text-[#0a192f]">
                        {c.measured_value.toFixed(asset.unit === "V" ? 8 : asset.unit === "dB" ? 5 : 5)} {asset.unit}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-slate-500">
                        {asset.category === "dcv_reference"
                          ? `${(c.mu_relative * 10.0 * 1e9).toFixed(1)} nV`
                          : asset.category === "ac_divider"
                          ? `${c.mu_relative.toFixed(1)} ppm`
                          : "—"}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-slate-700">
                        {c.error_ppm !== undefined ? `${c.error_ppm > 0 ? "+" : ""}${c.error_ppm.toFixed(2)} ppm` : "—"}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-slate-700">
                        {c.drift_ppm !== undefined && c.drift_ppm !== null
                          ? `${c.drift_ppm > 0 ? "+" : ""}${c.drift_ppm.toFixed(2)} ppm`
                          : "—"}
                      </td>

                      {/* Clean High-Contrast Acceptance Limit Chip (Zero Truncation) */}
                      <td className="py-2 px-3 text-center">
                        {c.lower !== null && c.upper !== null && c.lower !== undefined && c.upper !== undefined ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-slate-200 bg-slate-50 font-mono text-xs font-bold text-slate-800">
                            <span>{c.lower.toFixed(asset.unit === "V" ? 8 : 5)}</span>
                            <span className="text-slate-400 font-normal">↔</span>
                            <span>{c.upper.toFixed(asset.unit === "V" ? 8 : 5)}</span>
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>

                      {asset.category === "dcv_reference" && (
                        <>
                          <td className="py-2 px-3 text-xs font-semibold text-slate-700">{c.location || "—"}</td>
                          <td className="py-2 px-3 text-right font-mono text-slate-600">{c.pressure_hpa ? `${Math.round(c.pressure_hpa)} hPa` : "—"}</td>
                        </>
                      )}

                      <td className="py-2 px-3 text-center">
                        {c.display_status === "ok" ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            In Trend
                          </span>
                        ) : c.display_status === "reviewed_out_of_trend" ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                            Reviewed
                          </span>
                        ) : c.display_status === "out_of_trend" ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-300">
                            Out of Trend
                          </span>
                        ) : (
                          <span className="text-slate-400 text-xs">Baseline</span>
                        )}
                      </td>

                      <td className="py-2 px-3 text-center">
                        {c.reviewer_comment || c.reviewer_attachment_path ? (
                          <button
                            onClick={() =>
                              setActiveNote({
                                date: c.date,
                                comment: c.reviewer_comment || "No text comment recorded.",
                                attachPath: c.reviewer_attachment_path,
                                calId: c.id,
                              })
                            }
                            className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold"
                          >
                            Note
                          </button>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>

                      <td className="py-2 px-3 text-right">
                        <a
                          href={`/legacy/calibrations/${c.id}/edit${activeTpId ? `?tp=${activeTpId}` : ""}`}
                          className="px-2 py-0.5 rounded bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold"
                        >
                          Edit
                        </a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Inline Reviewer Note Modal */}
        {activeNote && (
          <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                <h4 className="text-base font-bold text-[#0a192f]">Reviewer Note — {activeNote.date}</h4>
                <button onClick={() => setActiveNote(null)} className="text-slate-400 hover:text-slate-600">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap mb-4">
                {activeNote.comment}
              </p>
              {activeNote.attachPath && (
                <div className="pt-3 border-t border-dashed border-slate-200">
                  <a
                    href={`/legacy/calibrations/${activeNote.calId}/attachment`}
                    target="_blank"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-md"
                  >
                    <FileText className="w-4 h-4" />
                    Open Attached File
                  </a>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}