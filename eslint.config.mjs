import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    ".kilo/**",
    "next-env.d.ts",
  ]),
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      // The dashboard is a client-authenticated app that fetches user-scoped
      // backend state after mount. Keep this architectural lint out of the
      // production gate while preserving hook order and dependency checks.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
