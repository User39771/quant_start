import fs from "node:fs/promises";
import path from "node:path";

const PROJECT_ROOT = path.resolve(import.meta.dirname, "..");
const DESIGN_DIR = path.join(
  PROJECT_ROOT,
  "reports",
  "robinhood_chain_pilot",
  "rq2_information_content_design",
);
const SESSION_DIR = path.join(
  PROJECT_ROOT,
  "reports",
  "robinhood_chain_pilot",
  "five_token_unbalanced_panel",
  "sessions",
);

const ALIGNED_PANEL = path.join(DESIGN_DIR, "rq2_primary_prospective_aligned_panel.csv");
const ELIGIBILITY = path.join(DESIGN_DIR, "rq2_price_free_row_level_eligibility.csv");
const PREDICTOR_OUTPUT = path.join(DESIGN_DIR, "rq2_primary_prospective_token_predictor.csv");
const ANALYSIS_OUTPUT = path.join(DESIGN_DIR, "rq2_primary_prospective_analysis_panel.csv");

const MIN_SWAPS = 5;
const MIN_NOTIONAL = 500;
const EXPECTED_COUNTS = { NVDA: 11, GME: 23, COST: 9 };
const TRUE = new Set(["true", "1", "yes"]);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (quoted) throw new Error("Unterminated quoted CSV field");
  if (field !== "" || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  if (rows.length === 0) return { headers: [], records: [] };
  const headers = rows[0].map((value, index) => (index === 0 ? value.replace(/^\uFEFF/, "") : value));
  const records = rows.slice(1).map((values, rowIndex) => {
    if (values.length !== headers.length) {
      throw new Error(`CSV width mismatch at data row ${rowIndex + 1}`);
    }
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
  return { headers, records };
}

function csvEscape(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function toCsv(headers, records) {
  const lines = [headers.map(csvEscape).join(",")];
  for (const record of records) {
    lines.push(headers.map((header) => csvEscape(record[header])).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

function isTrue(value) {
  return TRUE.has(String(value).trim().toLowerCase());
}

function keyOf(record) {
  return `${record.token}\u0000${record.market_open_date}`;
}

function requireColumns(headers, required, label) {
  const missing = required.filter((column) => !headers.includes(column));
  if (missing.length) throw new Error(`${label} missing columns: ${missing.join(", ")}`);
}

const formatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function newYorkParts(isoTimestamp) {
  const instant = new Date(isoTimestamp);
  if (!Number.isFinite(instant.valueOf())) throw new Error(`Invalid timestamp: ${isoTimestamp}`);
  const parts = Object.fromEntries(
    formatter.formatToParts(instant).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    seconds: Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second),
  };
}

function numeric(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`Non-finite ${label}: ${value}`);
  return number;
}

function compactNumber(number) {
  if (!Number.isFinite(number)) throw new Error(`Cannot serialize non-finite number: ${number}`);
  return number.toString();
}

async function readCsv(filePath) {
  return parseCsv(await fs.readFile(filePath, "utf8"));
}

async function reconstruct(record) {
  const swapsPath = path.join(SESSION_DIR, record.token, record.market_open_date, "decoded_swaps.csv");
  const swaps = await readCsv(swapsPath);
  requireColumns(
    swaps.headers,
    [
      "block_timestamp_et",
      "quote_amount_usdg",
      "underlying_equivalent_price_usdg",
      "reconstructable",
    ],
    swapsPath,
  );

  const prepared = swaps.records.map((swap) => ({ swap, ...newYorkParts(swap.block_timestamp_et) }));
  if (prepared.length === 0) throw new Error(`No decoded swaps for ${record.token} ${record.market_open_date}`);
  const priorDates = prepared.map((item) => item.date).filter((date) => date < record.market_open_date);
  if (priorDates.length === 0) throw new Error(`No prior-session date for ${record.token} ${record.market_open_date}`);
  const anchor20Date = priorDates.sort()[0];

  function anchor(date, lowerSeconds, upperSeconds, label) {
    const sample = prepared.filter(
      (item) =>
        item.date === date &&
        item.seconds >= lowerSeconds &&
        item.seconds < upperSeconds &&
        isTrue(item.swap.reconstructable),
    );
    let notional = 0;
    let weightedPrice = 0;
    for (const item of sample) {
      const quote = numeric(item.swap.quote_amount_usdg, `${label} quote notional`);
      const price = numeric(item.swap.underlying_equivalent_price_usdg, `${label} price`);
      notional += quote;
      weightedPrice += price * quote;
    }
    return {
      swapCount: sample.length,
      notional,
      vwap: notional > 0 ? weightedPrice / notional : Number.NaN,
    };
  }

  const p20 = anchor(anchor20Date, 19 * 3600 + 30 * 60, 20 * 3600, "20:00 anchor");
  const p04 = anchor(record.market_open_date, 3 * 3600 + 30 * 60, 4 * 3600, "04:00 anchor");
  const robust =
    Number.isFinite(p20.vwap) &&
    Number.isFinite(p04.vwap) &&
    p20.vwap > 0 &&
    p04.vwap > 0 &&
    p20.swapCount >= MIN_SWAPS &&
    p04.swapCount >= MIN_SWAPS &&
    p20.notional >= MIN_NOTIONAL &&
    p04.notional >= MIN_NOTIONAL;
  const deepReturn = robust ? Math.log(p04.vwap / p20.vwap) : Number.NaN;

  return { p20, p04, robust, deepReturn };
}

function countByToken(records) {
  return Object.fromEntries(
    Object.keys(EXPECTED_COUNTS).map((token) => [token, records.filter((record) => record.token === token).length]),
  );
}

async function validateWithArtifactTool(csvText, sheetName, expectedRows, expectedColumns) {
  const { Workbook } = await import("@oai/artifact-tool");
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const endColumn = columnName(expectedColumns);
  const inspection = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:${endColumn}${expectedRows + 1}`,
    include: "values,formulas",
    tableMaxRows: expectedRows + 1,
    tableMaxCols: expectedColumns,
  });
  if (!inspection?.ndjson) throw new Error(`Artifact-tool inspection failed for ${sheetName}`);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: `${sheetName} formula error scan`,
  });
  if (errors?.ndjson && /#(?:REF|DIV\/0|VALUE|NAME|N\/A|NUM|NULL|SPILL|CALC)/.test(errors.ndjson)) {
    throw new Error(`Artifact-tool formula error scan failed for ${sheetName}`);
  }
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

async function main() {
  const shouldWrite = process.argv.includes("--write");
  const aligned = await readCsv(ALIGNED_PANEL);
  const eligibility = await readCsv(ELIGIBILITY);
  requireColumns(
    aligned.headers,
    ["token", "market_open_date", "sample_role", "primary_inferential_row", "primary_stock_row_ok"],
    ALIGNED_PANEL,
  );
  requireColumns(
    eligibility.headers,
    ["token", "market_open_date", "token_deep_robust", "sample_role", "primary_inferential_row"],
    ELIGIBILITY,
  );

  const targetRows = aligned.records.filter(
    (record) =>
      record.sample_role === "PROSPECTIVE_EXTENSION" &&
      isTrue(record.primary_inferential_row) &&
      isTrue(record.primary_stock_row_ok),
  );
  const keys = targetRows.map(keyOf);
  const duplicateCount = keys.length - new Set(keys).size;
  const tokenCounts = countByToken(targetRows);
  if (targetRows.length !== 43 || duplicateCount !== 0 || JSON.stringify(tokenCounts) !== JSON.stringify(EXPECTED_COUNTS)) {
    throw new Error(`Frozen target mismatch: rows=${targetRows.length}, duplicates=${duplicateCount}, counts=${JSON.stringify(tokenCounts)}`);
  }

  const eligibilityByKey = new Map(eligibility.records.map((record) => [keyOf(record), record]));
  const predictorRows = [];
  const discrepancies = [];
  for (const stockRow of targetRows) {
    const eligibilityRow = eligibilityByKey.get(keyOf(stockRow));
    if (!eligibilityRow) throw new Error(`Missing eligibility row for ${stockRow.token} ${stockRow.market_open_date}`);
    if (
      !isTrue(eligibilityRow.token_deep_robust) ||
      eligibilityRow.sample_role !== "PROSPECTIVE_EXTENSION" ||
      !isTrue(eligibilityRow.primary_inferential_row)
    ) {
      throw new Error(`Frozen eligibility conflict for ${stockRow.token} ${stockRow.market_open_date}`);
    }
    const result = await reconstruct(stockRow);
    if (!result.robust) {
      discrepancies.push({
        token: stockRow.token,
        market_open_date: stockRow.market_open_date,
        frozen_token_deep_robust: true,
        reconstructed_token_deep_robust: false,
        swap_count_2000: result.p20.swapCount,
        notional_2000: result.p20.notional,
        swap_count_0400: result.p04.swapCount,
        notional_0400: result.p04.notional,
      });
      continue;
    }
    predictorRows.push({
      token: stockRow.token,
      market_open_date: stockRow.market_open_date,
      token_p20_30m: compactNumber(result.p20.vwap),
      token_p04_30m: compactNumber(result.p04.vwap),
      token_deep_return_30m: compactNumber(result.deepReturn),
      "30m_2000_swap_count": String(result.p20.swapCount),
      "30m_2000_notional": compactNumber(result.p20.notional),
      "30m_0400_swap_count": String(result.p04.swapCount),
      "30m_0400_notional": compactNumber(result.p04.notional),
      token_deep_robust: "true",
      sample_role: "PROSPECTIVE_EXTENSION",
      primary_inferential_row: "true",
    });
  }

  if (discrepancies.length) {
    console.log(JSON.stringify({ status: "STOP_FOR_RESEARCH_REVIEW", discrepancies }, null, 2));
    process.exitCode = 2;
    return;
  }

  const predictorHeaders = [
    "token",
    "market_open_date",
    "token_p20_30m",
    "token_p04_30m",
    "token_deep_return_30m",
    "30m_2000_swap_count",
    "30m_2000_notional",
    "30m_0400_swap_count",
    "30m_0400_notional",
    "token_deep_robust",
    "sample_role",
    "primary_inferential_row",
  ];
  const predictorByKey = new Map(predictorRows.map((record) => [keyOf(record), record]));
  const addedHeaders = predictorHeaders.filter((header) => !aligned.headers.includes(header));
  const analysisHeaders = [...aligned.headers, ...addedHeaders];
  const analysisRows = targetRows.map((stockRow) => {
    const predictor = predictorByKey.get(keyOf(stockRow));
    if (!predictor) throw new Error(`Missing predictor join for ${stockRow.token} ${stockRow.market_open_date}`);
    return { ...stockRow, ...Object.fromEntries(addedHeaders.map((header) => [header, predictor[header]])) };
  });

  const predictorCsv = toCsv(predictorHeaders, predictorRows);
  const analysisCsv = toCsv(analysisHeaders, analysisRows);
  const allFinite = predictorRows.every((record) =>
    ["token_p20_30m", "token_p04_30m", "token_deep_return_30m", "30m_2000_notional", "30m_0400_notional"].every(
      (field) => Number.isFinite(Number(record[field])),
    ),
  );
  const preservedStockValues = analysisRows.every((row, index) =>
    aligned.headers.every((header) => row[header] === targetRows[index][header]),
  );
  const qa = {
    status: "PASS",
    total_rows: analysisRows.length,
    rows_by_token: tokenCounts,
    duplicate_token_date_keys: duplicateCount,
    token_deep_return_30m_missing: predictorRows.filter((record) => record.token_deep_return_30m === "").length,
    all_token_predictor_values_finite: allFinite,
    all_token_deep_robust: predictorRows.every((record) => isTrue(record.token_deep_robust)),
    all_sample_role_prospective_extension: analysisRows.every((record) => record.sample_role === "PROSPECTIVE_EXTENSION"),
    all_primary_inferential_row: analysisRows.every((record) => isTrue(record.primary_inferential_row)),
    all_primary_stock_row_ok: analysisRows.every((record) => isTrue(record.primary_stock_row_ok)),
    discovery_rows: analysisRows.filter((record) => record.sample_role === "DISCOVERY").length,
    tsla_rows: analysisRows.filter((record) => record.token === "TSLA").length,
    frozen_robust_reconstruction_discrepancies: discrepancies.length,
    stock_side_values_preserved: preservedStockValues,
  };
  if (!Object.values(qa).every((value) => value !== false) || qa.token_deep_return_30m_missing !== 0) {
    throw new Error(`QA failure: ${JSON.stringify(qa)}`);
  }

  if (shouldWrite) {
    await validateWithArtifactTool(predictorCsv, "Predictors", predictorRows.length, predictorHeaders.length);
    await validateWithArtifactTool(analysisCsv, "AnalysisPanel", analysisRows.length, analysisHeaders.length);
    await fs.writeFile(PREDICTOR_OUTPUT, predictorCsv, "utf8");
    await fs.writeFile(ANALYSIS_OUTPUT, analysisCsv, "utf8");
  }
  console.log(JSON.stringify({ mode: shouldWrite ? "write" : "dry-run", ...qa }, null, 2));
}

await main();
