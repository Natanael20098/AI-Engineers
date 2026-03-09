import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AppConfig {
  env: string;
  app: {
    name: string;
    version: string;
    port: number;
    logLevel: string;
  };
  server: {
    host: string;
    requestTimeoutMs: number;
    maxRequestBodySizeKb: number;
  };
  security: {
    bcryptSaltRounds: number;
    jwtSecret: string;
    jwtExpiresIn: string;
    corsAllowedOrigins: string[];
  };
  database: {
    url: string;
    poolMin: number;
    poolMax: number;
    acquireTimeoutMs: number;
    idleTimeoutMs: number;
  };
  rateLimit: {
    windowMs: number;
    maxRequests: number;
  };
  cache: {
    ttlSeconds: number;
    redisUrl?: string;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PROJECT_ROOT = path.resolve(__dirname, "..");

/**
 * Resolves and loads the .env file that matches the current NODE_ENV.
 * Falls back to `.env` if a specific file is not found.
 *
 * Supported values for NODE_ENV: development | testing | production
 */
function loadEnvFile(nodeEnv: string): void {
  const envFileName = `.env.${nodeEnv}`;
  const envFilePath = path.join(PROJECT_ROOT, envFileName);
  const fallbackPath = path.join(PROJECT_ROOT, ".env");

  if (fs.existsSync(envFilePath)) {
    dotenv.config({ path: envFilePath });
    console.log(`[ConfigLoader] Loaded environment file: ${envFileName}`);
  } else if (fs.existsSync(fallbackPath)) {
    dotenv.config({ path: fallbackPath });
    console.warn(
      `[ConfigLoader] Environment file '${envFileName}' not found — fell back to '.env'`
    );
  } else {
    console.warn(
      `[ConfigLoader] No .env file found for NODE_ENV='${nodeEnv}'. ` +
        `Relying solely on process environment variables.`
    );
  }
}

/**
 * Reads and parses configurations/baseConfig.json, which provides
 * non-sensitive defaults for every environment.
 */
function loadBaseConfig(): Record<string, unknown> {
  const baseConfigPath = path.join(PROJECT_ROOT, "configurations", "baseConfig.json");
  if (!fs.existsSync(baseConfigPath)) {
    throw new Error(
      `[ConfigLoader] baseConfig.json not found at: ${baseConfigPath}`
    );
  }
  const raw = fs.readFileSync(baseConfigPath, "utf8");
  return JSON.parse(raw) as Record<string, unknown>;
}

/**
 * Retrieves a required environment variable.
 * Throws a descriptive error when the variable is absent — prevents the
 * application from starting with an incomplete configuration.
 */
function requireEnv(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(
      `[ConfigLoader] Required environment variable '${key}' is not set. ` +
        `Ensure the correct .env file is present or the variable is exported.`
    );
  }
  return value;
}

/**
 * Parses a comma-separated env var into a string array.
 */
function parseList(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Main loader
// ---------------------------------------------------------------------------

let cachedConfig: AppConfig | null = null;

/**
 * Loads, merges, and validates the application configuration.
 *
 * Resolution order (later values win):
 *   1. configurations/baseConfig.json  — non-sensitive defaults
 *   2. .env.<NODE_ENV>                 — environment-specific overrides
 *   3. process.env                     — runtime / container variables
 *
 * Call `loadConfig()` once during application startup.  Subsequent calls
 * return the cached instance unless `forceReload` is set to `true`.
 */
export function loadConfig(forceReload = false): AppConfig {
  if (cachedConfig && !forceReload) {
    return cachedConfig;
  }

  const nodeEnv = (process.env.NODE_ENV ?? "development").toLowerCase();

  // Validate that NODE_ENV is a recognised environment
  const allowedEnvs = ["development", "testing", "production"];
  if (!allowedEnvs.includes(nodeEnv)) {
    throw new Error(
      `[ConfigLoader] Invalid NODE_ENV '${nodeEnv}'. Must be one of: ${allowedEnvs.join(", ")}`
    );
  }

  // Step 1 — load .env.<NODE_ENV> file
  loadEnvFile(nodeEnv);

  // Step 2 — load baseConfig.json defaults
  const base = loadBaseConfig() as {
    app: AppConfig["app"];
    server: AppConfig["server"];
    security: Omit<AppConfig["security"], "jwtSecret">;
    database: Omit<AppConfig["database"], "url">;
    rateLimit: AppConfig["rateLimit"];
    cache: Omit<AppConfig["cache"], "redisUrl">;
  };

  // Step 3 — merge with environment variables (env vars override base config)
  const config: AppConfig = {
    env: nodeEnv,

    app: {
      name: process.env.APP_NAME ?? base.app.name,
      version: process.env.APP_VERSION ?? base.app.version,
      port: Number(process.env.PORT ?? base.app.port),
      logLevel: process.env.LOG_LEVEL ?? base.app.logLevel,
    },

    server: {
      host: process.env.HOST ?? base.server.host,
      requestTimeoutMs: Number(
        process.env.REQUEST_TIMEOUT_MS ?? base.server.requestTimeoutMs
      ),
      maxRequestBodySizeKb: Number(
        process.env.MAX_REQUEST_BODY_SIZE_KB ?? base.server.maxRequestBodySizeKb
      ),
    },

    security: {
      bcryptSaltRounds: Number(
        process.env.BCRYPT_SALT_ROUNDS ?? base.security.bcryptSaltRounds
      ),
      // Sensitive — must come from environment, never from baseConfig
      jwtSecret: requireEnv("JWT_SECRET"),
      jwtExpiresIn: process.env.JWT_EXPIRES_IN ?? base.security.jwtExpiresIn,
      corsAllowedOrigins:
        parseList(process.env.CORS_ALLOWED_ORIGINS) ||
        base.security.corsAllowedOrigins,
    },

    database: {
      // Sensitive — must come from environment, never from baseConfig
      url: requireEnv("DATABASE_URL"),
      poolMin: Number(process.env.DB_POOL_MIN ?? base.database.poolMin),
      poolMax: Number(process.env.DB_POOL_MAX ?? base.database.poolMax),
      acquireTimeoutMs: Number(
        process.env.DB_ACQUIRE_TIMEOUT_MS ?? base.database.acquireTimeoutMs
      ),
      idleTimeoutMs: Number(
        process.env.DB_IDLE_TIMEOUT_MS ?? base.database.idleTimeoutMs
      ),
    },

    rateLimit: {
      windowMs: Number(
        process.env.RATE_LIMIT_WINDOW_MS ?? base.rateLimit.windowMs
      ),
      maxRequests: Number(
        process.env.RATE_LIMIT_MAX_REQUESTS ?? base.rateLimit.maxRequests
      ),
    },

    cache: {
      ttlSeconds: Number(process.env.CACHE_TTL_SECONDS ?? base.cache.ttlSeconds),
      redisUrl: process.env.REDIS_URL,
    },
  };

  // Step 4 — startup diagnostics (non-sensitive fields only)
  console.log("[ConfigLoader] Configuration loaded successfully:");
  console.log(`  NODE_ENV         : ${config.env}`);
  console.log(`  App name         : ${config.app.name}`);
  console.log(`  App version      : ${config.app.version}`);
  console.log(`  Port             : ${config.app.port}`);
  console.log(`  Log level        : ${config.app.logLevel}`);
  console.log(`  Host             : ${config.server.host}`);
  console.log(`  DB pool (min/max): ${config.database.poolMin}/${config.database.poolMax}`);
  console.log(`  Rate limit       : ${config.rateLimit.maxRequests} req / ${config.rateLimit.windowMs}ms`);
  console.log(`  Cache TTL        : ${config.cache.ttlSeconds}s`);

  cachedConfig = config;
  return config;
}

/**
 * Returns the cached configuration.
 * Throws if `loadConfig()` has not been called yet.
 */
export function getConfig(): AppConfig {
  if (!cachedConfig) {
    throw new Error(
      "[ConfigLoader] Configuration has not been loaded yet. Call loadConfig() first."
    );
  }
  return cachedConfig;
}
