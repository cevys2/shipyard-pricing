// Jalankan dari folder frontend: `npm test`
// Tidak butuh paket tambahan -- Node 22 sudah bisa membaca TypeScript langsung.
import { test } from "node:test";
import assert from "node:assert/strict";
import { cekBerkas } from "../src/lib/berkas.ts";

const EXCEL = [".xlsx", ".xls"];

test("berkas Excel biasa diterima", () => {
  assert.equal(cekBerkas("REALISASI BIAYA DOCKING MISHIMA.xlsx", EXCEL), null);
  assert.equal(cekBerkas("repair list antareja.xls", EXCEL), null);
});

test("huruf besar di ekstensi tetap diterima", () => {
  // Berkas kiriman klien sering bernama "LAMPIRAN.XLSX".
  assert.equal(cekBerkas("LAMPIRAN PERJANJIAN.XLSX", EXCEL), null);
});

test("nama yang mengandung titik dan kurung tetap dibaca dari ekstensi terakhirnya", () => {
  assert.equal(cekBerkas("KMP. PRATHITA IV (1).xlsx", EXCEL), null);
});

test("CSV diterima hanya kalau memang ada di daftar", () => {
  assert.equal(cekBerkas("data.csv", [".xlsx", ".xls", ".csv"]), null);
  assert.notEqual(cekBerkas("data.csv", EXCEL), null);
});

test("berkas yang bukan Excel ditolak, dan pesannya menyebut apa yang salah", () => {
  const pesan = cekBerkas("foto kapal.pdf", EXCEL);
  assert.equal(typeof pesan, "string");
  assert.ok(pesan!.includes(".pdf"), `pesan harus menyebut ".pdf": ${pesan}`);
  assert.ok(pesan!.includes(".xlsx"), `pesan harus menyebut berkas yang diterima: ${pesan}`);
});

test("ekstensi ganda: yang menentukan adalah yang paling belakang", () => {
  assert.notEqual(cekBerkas("repair list.xlsx.pdf", EXCEL), null);
});

test("berkas tanpa ekstensi ditolak dengan pesan yang tetap masuk akal", () => {
  const pesan = cekBerkas("repair list", EXCEL);
  assert.equal(typeof pesan, "string");
  assert.ok(pesan!.includes(".xlsx"), `pesan harus menyebut berkas yang diterima: ${pesan}`);
});
