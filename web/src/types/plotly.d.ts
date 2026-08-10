// `plotly.js-dist-min` ships no type declarations of its own, and there is
// no matching @types package. Typing Plotly's full API (traces, layouts,
// config, event payloads, ...) is a large surface with little payoff here —
// this codebase only calls a handful of methods (`newPlot`, `react`, `purge`)
// with plain object literals. Keep this declaration deliberately loose
// (`any`) rather than "improving" it into a partial API surface that will
// always be behind what the library actually supports.
declare module 'plotly.js-dist-min' {
  const Plotly: any;
  // CommonJS-style `export =` (not `export default`): this package's dist
  // build is a single UMD object, and call sites use dynamic
  // `import('plotly.js-dist-min').then(Plotly => Plotly.newPlot(...))`.
  // With `export =` + esModuleInterop, TS resolves the dynamic import's
  // awaited value to `Plotly` itself (methods directly on it), matching
  // how it actually loads at runtime — `export default Plotly` would
  // instead require `(await import(...)).default.newPlot(...)`.
  export = Plotly;
}
