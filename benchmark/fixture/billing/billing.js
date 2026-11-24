export const invoiceTotal = (lines) => lines.reduce((a, b) => a + b, 0);
export function refreshToken(tok) {
  return { ...tok, exp: tok.exp + 3600, scope: tok.scope.split(" ")[0] }; // bug: drops every scope after the first
}
