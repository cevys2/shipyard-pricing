/**
 * Parses text pasted from Excel/Sheets (tab-separated columns, newline-separated rows)
 * into an array of row arrays. Handles \r\n line endings and trims trailing empty rows.
 */
export function parseTsv(text: string): string[][] {
  const rows = text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.split("\t").map((cell) => cell.trim()))
    .filter((cells) => cells.some((c) => c !== ""));
  return rows;
}
