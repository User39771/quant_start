import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(import.meta.dirname, "..");
const OUTPUT_DIR = path.join(
  ROOT,
  "reports",
  "robinhood_chain_pilot",
  "rq2_information_content_design",
  "e1_stability_map",
);
const payload = JSON.parse(await fs.readFile(path.join(OUTPUT_DIR, "e1_stability_payload.json"), "utf8"));

function escapeCsv(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function csvFromRows(headers, rows) {
  return `${[
    headers.map(escapeCsv).join(","),
    ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(",")),
  ].join("\r\n")}\r\n`;
}

function columnName(count) {
  let name = "";
  for (let value = count; value > 0; value = Math.floor((value - 1) / 26)) {
    name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  }
  return name;
}

async function validate(csvText, sheetName, rows, columns) {
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const table = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:${columnName(columns)}${rows + 1}`,
    include: "values,formulas",
    tableMaxRows: rows + 1,
    tableMaxCols: columns,
  });
  if (!table?.ndjson) throw new Error(`Artifact-tool inspection failed for ${sheetName}`);
}

const common = [
  "n",
  "token_beta",
  "token_hc3_standard_error",
  "token_ci_95_lower",
  "token_ci_95_upper",
  "token_p_value",
  "model_0_r_squared",
  "model_0_adjusted_r_squared",
  "model_1_r_squared",
  "model_1_adjusted_r_squared",
  "delta_r_squared",
  "delta_adjusted_r_squared",
  "token_partial_r_squared",
  "fixed_effect_reference_asset",
  "estimator",
  "uncertainty",
  "reference_distribution",
  "model_0_formula",
  "model_1_formula",
  "beta_change_from_frozen",
  "absolute_beta_change_from_frozen",
];

const outputs = [
  {
    file: "e1_leave_one_session_out.csv",
    sheet: "LeaveOneSessionOut",
    rows: payload.leave_one_session_out,
    headers: [
      "sensitivity_label",
      "omitted_asset",
      "omitted_market_open_date",
      "remaining_assets",
      ...common,
    ],
  },
  {
    file: "e1_leave_one_asset_out.csv",
    sheet: "LeaveOneAssetOut",
    rows: payload.leave_one_asset_out,
    headers: ["sensitivity_label", "omitted_asset", "remaining_assets", ...common],
  },
  {
    file: "e1_influence_stress.csv",
    sheet: "InfluenceStress",
    rows: payload.influence_stress,
    headers: [
      "sensitivity_label",
      "omitted_observation_count",
      "omitted_observations",
      "remaining_assets",
      ...common,
    ],
  },
];

for (const output of outputs) {
  const csvText = csvFromRows(output.headers, output.rows);
  await validate(csvText, output.sheet, output.rows.length, output.headers.length);
  await fs.writeFile(path.join(OUTPUT_DIR, output.file), csvText, "utf8");
}

console.log(JSON.stringify(Object.fromEntries(outputs.map((item) => [item.file, item.rows.length])), null, 2));
