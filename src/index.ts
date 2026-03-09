import { loadConfig } from "./ConfigLoader";

// Load and validate configuration at startup.
// This is the single entry point for all environment-specific settings.
const config = loadConfig();

// Application bootstrap continues here after successful configuration load.
console.log(
  `[App] ZCloud Security Platform starting in '${config.env}' environment on port ${config.app.port} ...`
);

export { config };
