import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(import.meta.dirname, "..");
const DESIGN_DIR = path.join(
  ROOT,
  "reports",
  "robinhood_chain_pilot",
  "rq2_information_content_design",
);
const results = JSON.parse(
  await fs.readFile(path.join(DESIGN_DIR, "rq2_primary_prospective_results.json"), "utf8"),
);

function escapeCsv(value) {
  if (value === null || value === undefined) return '""';
  return `"${String(value).replaceAll('"', '""')}"`;
}

function csvFromRows(headers, rows) {
  const lines = [headers.map(escapeCsv).join(",")];
  for (const row of rows) lines.push(headers.map((header) => escapeCsv(row[header])).join(","));
  return `${lines.join("\r\n")}\r\n`;
}

function columnName(count) {
  let name = "";
  let value = count;
  while (value > 0) {
    value -= 1;
    name = String.fromCharCode(65 + (value % 26)) + name;
    value = Math.floor(value / 26);
  }
  return name;
}

async function validate(csvText, sheetName, rowCount, columnCount) {
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const inspected = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:${columnName(columnCount)}${rowCount + 1}`,
    include: "values,formulas",
    tableMaxRows: rowCount + 1,
    tableMaxCols: columnCount,
  });
  if (!inspected?.ndjson) throw new Error(`Artifact-tool inspection failed for ${sheetName}`);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: `${sheetName} formula error scan`,
  });
  if (errors?.ndjson && /#(?:REF|DIV\/0|VALUE|NAME|N\/A|NUM|NULL|SPILL|CALC)/.test(errors.ndjson)) {
    throw new Error(`Formula error found in ${sheetName}`);
  }
}

const outputs = [
  {
    file: "rq2_primary_prospective_model_coefficients.csv",
    sheet: "ModelCoefficients",
    rows: results.model_coefficients,
    headers: [
      "model_id",
      "term",
      "estimate",
      "hc3_standard_error",
      "ci_95_lower",
      "ci_95_upper",
      "p_value",
      "n",
      "df_residual",
      "r_squared",
      "adjusted_r_squared",
      "uncertainty",
      "reference_distribution",
      "reference_asset",
    ],
  },
  {
    file: "rq2_primary_prospective_asset_diagnostics.csv",
    sheet: "AssetDiagnostics",
    rows: results.asset_diagnostics,
    headers: [
      "token",
      "n",
      "date_start",
      "date_end",
      "pearson_correlation",
      "spearman_correlation",
      "sign_agreement_rate",
      "sign_agreement_denominator",
      "zero_sign_rows_excluded",
      "simple_beta",
      "simple_beta_hc3_standard_error",
      "simple_beta_ci_95_lower",
      "simple_beta_ci_95_upper",
      "simple_beta_p_value",
      "simple_model_r_squared",
      "uncertainty",
      "reference_distribution",
    ],
  },
  {
    file: "rq2_primary_prospective_influence_diagnostics.csv",
    sheet: "InfluenceDiagnostics",
    rows: results.influence_diagnostics,
    headers: [
      "token",
      "market_open_date",
      "leverage",
      "externally_studentized_residual",
      "cooks_distance",
      "high_leverage_flag",
      "large_studentized_residual_flag",
      "large_cooks_distance_flag",
      "unusually_influential_flag",
    ],
  },
];

for (const output of outputs) {
  const csvText = csvFromRows(output.headers, output.rows);
  await validate(csvText, output.sheet, output.rows.length, output.headers.length);
  await fs.writeFile(path.join(DESIGN_DIR, output.file), csvText, "utf8");
}

console.log(
  JSON.stringify(
    Object.fromEntries(outputs.map((output) => [output.file, output.rows.length])),
    null,
    2,
  ),
);
