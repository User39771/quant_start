import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(import.meta.dirname, "..");
const outputDir = path.join(ROOT, "reports", "robinhood_chain_pilot", "rq2_information_content_design", "e3_temporal_localization");
const payload = JSON.parse(await fs.readFile(path.join(outputDir, "e3_payload.json"), "utf8"));
const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const csvFromRows = (headers, rows) => `${[headers.map(escapeCsv).join(","), ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(","))].join("\r\n")}\r\n`;
const columnName = (count) => { let name = ""; for (let value = count; value > 0; value = Math.floor((value - 1) / 26)) name = String.fromCharCode(65 + ((value - 1) % 26)) + name; return name; };
async function writeCsv(file, sheetName, rows, headers) {
  const csvText = csvFromRows(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const inspected = await workbook.inspect({ kind: "table", range: `${sheetName}!A1:${columnName(headers.length)}${rows.length + 1}`, include: "values,formulas", tableMaxRows: rows.length + 1, tableMaxCols: headers.length });
  if (!inspected?.ndjson) throw new Error(`Artifact-tool inspection failed for ${file}`);
  await fs.writeFile(path.join(outputDir, file), csvText, "utf8");
}

const auditHeaders = ["asset", "market_open_date", "frozen_primary_member", "stock_p20", "stock_premarket", "stock_open", "premarket_raw_trade_count", "premarket_eligible_trade_count", "premarket_shares", "premarket_notional", "premarket_first_trade_time", "premarket_last_trade_time", "premarket_last_trade_age_seconds", "premarket_exact_interval_requested", "premarket_pagination_complete", "premarket_all_rows_inside_interval", "premarket_timestamps_timezone_aware", "premarket_all_conditions_classified", "premarket_minimum_5_executions", "premarket_minimum_100_shares", "premarket_minimum_10000_notional", "premarket_finite_positive_vwap", "premarket_staleness_warning", "premarket_anomaly_review_required", "premarket_unknown_condition_codes", "premarket_duplicate_trade_id_count", "premarket_missing_required_trade_field_count", "premarket_nonpositive_price_or_size_count", "e3_eligible", "e3_failure_reason", "source", "feed", "premarket_window", "condition_policy_sha256"];
const modelHeaders = ["analysis_scope", "outcome", "model_0_id", "model_1_id", "n", "asset_counts", "reference_asset", "token_beta", "token_hc3_standard_error", "token_ci_95_lower", "token_ci_95_upper", "token_p_value", "model_0_r_squared", "model_0_adjusted_r_squared", "model_1_r_squared", "model_1_adjusted_r_squared", "delta_r_squared", "delta_adjusted_r_squared", "token_partial_r_squared", "estimator", "uncertainty", "reference_distribution", "model_0_formula", "model_1_formula"];
const nvdaHeaders = ["analysis_label", "outcome", "n", "status", "token_beta", "token_hc3_standard_error", "token_ci_95_lower", "token_ci_95_upper", "token_p_value", "r_squared", "adjusted_r_squared", "estimator", "uncertainty"];
const outputs = [
  ["e3_premarket_row_audit.csv", "PremarketAudit", payload.row_audit, auditHeaders],
  ["e3_temporal_model_results.csv", "TemporalModels", payload.temporal_model_results, modelHeaders],
  ["e3_nvda_temporal_descriptive.csv", "NVDADescriptive", payload.nvda_temporal_descriptive, nvdaHeaders],
];
for (const [file, sheet, rows, headers] of outputs) await writeCsv(file, sheet, rows, headers);
console.log(JSON.stringify(Object.fromEntries(outputs.map(([file, , rows]) => [file, rows.length])), null, 2));
