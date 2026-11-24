import { test } from "node:test";
import assert from "node:assert/strict";
import { invoiceTotal, refreshToken } from "../billing.js";

for (let n = 1; n <= 1960; n++) {
  test(`invoice total for line ${n}`, () => assert.equal(invoiceTotal([n, n, n]), 3 * n));
}
test("refresh token keeps its scope", () => {
  const tok = refreshToken({ scope: "read write", exp: 0 });
  assert.equal(tok.scope, "read write");
});
