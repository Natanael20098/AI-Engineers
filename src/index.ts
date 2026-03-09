import { createServer } from './config/serverConfig';

const PORT = parseInt(process.env.PORT ?? '3000', 10);
const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
  console.error('[FATAL] JWT_SECRET environment variable is required');
  process.exit(1);
}

const app = createServer({
  port: PORT,
  jwtSecret: JWT_SECRET,
  requiredRoles: [],
});

app.listen(PORT, () => {
  console.log(`[ZCloud Security Platform] Server listening on port ${PORT}`);
});
