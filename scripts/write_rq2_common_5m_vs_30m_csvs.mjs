import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(import.meta.dirname, "..");
const outputDir = path.join(ROOT, "reports", "robinhood_chain_pilot", "rq2_information_content_design", "common_5m_vs_30m");
const payload = JSON.parse(await fs.readFile(path.join(outputDir, "common_5m_vs_30m_payload.json"), "utf8"));
const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const csvFromRows = (headers, rows) => `${[headers.map(escapeCsv).join(","), ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(","))].join("\r\n")}\r\n`;
const columnName = (count) => { let name = ""; for (let value = count; value > 0; value = Math.floor((value - 1) / 26)) name = String.fromCharCode(65 + ((value - 1) % 26)) + name; return name; };

async function writeCsv(file, sheetName, rows, headers) {
  const csvText = csvFromRows(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const inspected = await workbook.inspect({ kind: "table", range: `${sheetName}!A1:${columnName(headers.length)}${rows.length + 1}`, include: "values,formulas", tableMaxRows: rows.length + 1, tableMaxCols: headers.length });
  if (!inspected?.ndjson) throw new Error(`Artifact-tool inspection failed for ${file}`);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: `${sheetName} formula error scan` });
  if (errors?.ndjson && /#(?:REF|DIV\/0|VALUE|NAME|N\/A|NUM|NULL|SPILL|CALC)/.test(errors.ndjson)) throw new Error(`Artifact-tool formula error scan failed for ${file}`);
  await fs.writeFile(path.join(outputDir, file), csvText, "utf8");
}

const auditHeaders = ["asset", "market_open_date", "frozen_primary_member", "token_p20_30m", "token_p04_30m", "token_deep_return_30m", "token_p20_5m", "token_p04_5m", "token_deep_return_5m", "strict_5m_2000_window", "strict_5m_0400_window", "strict_5m_2000_swap_count", "strict_5m_2000_quote_notional_usdg", "strict_5m_2000_measurable", "strict_5m_0400_swap_count", "strict_5m_0400_quote_notional_usdg", "strict_5m_0400_measurable", "strict_5m_measurement_row_crosscheck", "strict_5m_eligible", "strict_5m_failure_reason", "common_session_member", "stock_post_return", "stock_20_to_open_return"];
const predictorHeaders = ["metric", "value"];
const modelHeaders = ["analysis_scope", "predictor", "n", "asset_counts", "reference_asset", "token_beta", "token_hc3_standard_error", "token_ci_95_lower", "token_ci_95_upper", "token_p_value", "model_0_r_squared", "model_0_adjusted_r_squared", "model_0_sse", "model_1_r_squared", "model_1_adjusted_r_squared", "model_1_sse", "delta_r_squared", "delta_adjusted_r_squared", "token_partial_r_squared", "estimator", "uncertainty", "reference_distribution", "model_0_formula", "model_1_formula", "sample_composition_beta_change", "estimator_beta_change", "sample_composition_delta_r_squared_change", "estimator_delta_r_squared_change", "sample_composition_delta_adjusted_r_squared_change", "estimator_delta_adjusted_r_squared_change", "sample_composition_partial_r_squared_change", "estimator_partial_r_squared_change"];
const outputs = [
  ["common_5m_vs_30m_row_audit.csv", "RowAudit", payload.row_audit, auditHeaders],
  ["common_5m_vs_30m_predictor_comparison.csv", "PredictorComparison", payload.predictor_comparison, predictorHeaders],
  ["common_5m_vs_30m_model_results.csv", "ModelResults", payload.model_results, modelHeaders],
];
for (const [file, sheet, rows, headers] of outputs) await writeCsv(file, sheet, rows, headers);
console.log(JSON.stringify(Object.fromEntries(outputs.map(([file, , rows]) => [file, rows.length])), null, 2));
