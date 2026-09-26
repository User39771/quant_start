import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(import.meta.dirname, "..");
const outputDir = path.join(ROOT, "reports", "robinhood_chain_pilot", "rq2_information_content_design", "e2_nvda_identity_vs_liquidity");
const payload = JSON.parse(await fs.readFile(path.join(outputDir, "e2_payload.json"), "utf8"));

const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const csvFromRows = (headers, rows) => `${[headers.map(escapeCsv).join(","), ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(","))].join("\r\n")}\r\n`;
const columnName = (count) => {
  let name = "";
  for (let value = count; value > 0; value = Math.floor((value - 1) / 26)) name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  return name;
};

async function writeCsv(file, sheetName, rows, headers) {
  const csvText = csvFromRows(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const inspected = await workbook.inspect({ kind: "table", range: `${sheetName}!A1:${columnName(headers.length)}${rows.length + 1}`, include: "values,formulas", tableMaxRows: rows.length + 1, tableMaxCols: headers.length });
  if (!inspected?.ndjson) throw new Error(`Artifact-tool inspection failed for ${file}`);
  await fs.writeFile(path.join(outputDir, file), csvText, "utf8");
}

const outputs = [
  ["e2_liquidity_row_audit.csv", "LiquidityAudit", payload.row_audit, ["asset", "market_open_date", "sample_role", "primary_inferential_row", "swap_count_20", "quote_notional_20", "swap_count_04", "quote_notional_04", "weak_anchor_notional", "L_raw", "L_z", "token_deep_return_30m", "stock_post_return", "stock_20_to_open_return"]],
  ["e2_asset_liquidity_summary.csv", "AssetLiquidity", payload.asset_liquidity_summary, ["asset", "variable", "n", "minimum", "percentile_25", "median", "percentile_75", "maximum", "mean", "standard_deviation"]],
  ["e2_model_results.csv", "ModelResults", payload.model_results, ["model_id", "term", "estimate", "hc3_standard_error", "ci_95_lower", "ci_95_upper", "p_value", "n", "df_residual", "r_squared", "adjusted_r_squared", "change_r_squared_vs_frozen_model_1", "change_adjusted_r_squared_vs_frozen_model_1", "design_rank", "parameter_count", "estimator", "uncertainty", "reference_distribution", "asset_fixed_effects"]],
  ["e2_marginal_token_slopes.csv", "MarginalSlopes", payload.marginal_token_slopes, ["model_id", "asset_scope", "liquidity_point", "L_z", "token_slope", "hc3_standard_error", "ci_95_lower", "ci_95_upper", "p_value", "n", "estimator", "uncertainty"]],
];

for (const [file, sheet, rows, headers] of outputs) await writeCsv(file, sheet, rows, headers);
console.log(JSON.stringify(Object.fromEntries(outputs.map(([file, , rows]) => [file, rows.length])), null, 2));
