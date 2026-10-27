// Jalankan dari folder frontend: `npm test`
import { test } from "node:test";
import assert from "node:assert/strict";
import { AWALAN_KAPAL, AWALAN_PERUSAHAAN, rapikanNama } from "../src/lib/nama.ts";

const kapal = (t: string, ada: string[] = []) => rapikanNama(t, AWALAN_KAPAL, ada);
const pt = (t: string, ada: string[] = []) => rapikanNama(t, AWALAN_PERUSAHAAN, ada);

test("huruf besar dan spasi ganda dirapikan", () => {
  assert.equal(kapal("kmp.  prima   nusantara "), "KMP. PRIMA NUSANTARA");
});

test("awalan yang ditulis tanpa titik diberi titik", () => {
  assert.equal(kapal("KMP PRATHITA IV"), "KMP. PRATHITA IV");
  assert.equal(kapal("kn sar 207"), "KN. SAR 207");
  assert.equal(kapal("MV.BALI HAI II"), "MV. BALI HAI II");
  assert.equal(pt("pt munic line"), "PT. MUNIC LINE");
});

test("awalan tidak ditambahkan kalau tidak ditulis", () => {
  assert.equal(kapal("marina segunda"), "MARINA SEGUNDA");
  assert.equal(pt("basarnas"), "BASARNAS");
});

test("kata yang cuma diawali huruf awalan tidak dianggap awalan", () => {
  assert.equal(kapal("KMPX JAYA"), "KMPX JAYA");
  assert.equal(kapal("KMPX"), "KMPX");
  assert.equal(pt("PTERA LAUT"), "PTERA LAUT");
  assert.equal(pt("PT"), "PT");
});

test("ejaan yang sudah tersimpan menang kalau bedanya cuma titik atau spasi", () => {
  const ada = ["KMP PRATHITA IV", "KMP. GILIMANUK"];
  assert.equal(kapal("kmp. prathita iv", ada), "KMP PRATHITA IV");
  assert.equal(kapal("kmp gilimanuk", ada), "KMP. GILIMANUK");
  assert.equal(pt("pt. munic line", ["PT MUNIC LINE"]), "PT MUNIC LINE");
});

test("nama baru yang tidak mirip apa pun tetap dirapikan biasa", () => {
  assert.equal(kapal("kmp gilimanuk ii", ["KMP. GILIMANUK"]), "KMP. GILIMANUK II");
});
