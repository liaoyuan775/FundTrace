import { expect, test } from "vitest";
import { readFileSync } from "node:fs";

const styles = readFileSync("src/styles.css", "utf8");

test("keeps topbar branding light and light controls dark", () => {
  expect(styles).toMatch(
    /\.topbar\s*\{[^}]*background:\s*var\(--ink\);[^}]*color:\s*#ffffff;/s,
  );
  expect(styles).toMatch(
    /\.case-switch select,[^}]*background:\s*var\(--ink3\);[^}]*color:\s*#17324d;/s,
  );
  expect(styles).toMatch(
    /\.topbar \.brand span,[^}]*\.topbar \.case-switch span,[^}]*\.topbar \.disclaimer\s*\{[^}]*color:\s*#b8cee1;/s,
  );
  expect(styles).toMatch(
    /\.case-form input,[^}]*\.date-pair input\s*\{[^}]*border:\s*1px solid #9eb8cf;[^}]*color:\s*#17324d;/s,
  );
});

test("uses blue navigation and readable light-surface details", () => {
  expect(styles).toMatch(
    /@media \(max-width: 700px\)[\s\S]*?\.rail button\.active\s*\{[^}]*border-bottom-color:\s*var\(--cyan\);/s,
  );
  expect(styles).toMatch(/\.attribution-note\s*\{[^}]*color:\s*#5d7488;/s);
  expect(styles).toMatch(
    /\.risk-rules > div\s*\{[^}]*border-bottom:\s*1px solid var\(--line\);/s,
  );
  expect(styles).toMatch(/\.risk-rules strong\s*\{[^}]*color:\s*#a72d36;/s);
  expect(styles).toMatch(
    /@media \(max-width: 700px\)[\s\S]*?\.case-switch\s*\{[^}]*flex:\s*0 0 100%;/s,
  );
});

test("uses a soft light-blue navigation rail", () => {
  expect(styles).toMatch(
    /\.rail\s*\{[^}]*background:\s*var\(--ink3\);/s,
  );
  expect(styles).toMatch(
    /\.rail button\s*\{[^}]*color:\s*#355873;/s,
  );
  expect(styles).toMatch(
    /\.rail button:hover\s*\{[^}]*color:\s*#123b63;[^}]*background:\s*#dce9f5;/s,
  );
  expect(styles).toMatch(
    /\.rail button\.active\s*\{[^}]*color:\s*#123b63;[^}]*border-left-color:\s*var\(--cyan\);[^}]*background:\s*#cfe5f7;/s,
  );
});

test("keeps the topology canvas free of decorative grid lines", () => {
  expect(styles).not.toContain("background-image:");
  expect(styles).not.toContain("background-size:");
});

test("lets the transaction panel collapse to its title and table header", () => {
  expect(styles).toMatch(
    /grid-template-rows:\s*minmax\(180px, var\(--graph-height, 1fr\)\) 8px minmax\(74px, 1fr\);/,
  );
});
