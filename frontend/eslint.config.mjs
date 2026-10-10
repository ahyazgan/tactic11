import nextVitals from "eslint-config-next/core-web-vitals";

export default [
  ...nextVitals,
  {
    // Adopt the new lint command without making existing presentation/Compiler
    // diagnostics a release gate. Hooks correctness remains an error; the
    // React Compiler is not enabled in this application.
    rules: {
      "react/no-unescaped-entities": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
];
