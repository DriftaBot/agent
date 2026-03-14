#!/usr/bin/env bash
# Generate OpenAPI schema from a NestJS project using SwaggerModule.
# Mocks TypeORM DataSource.initialize so no real database is needed.
set -euo pipefail

OUTPUT="${1:?Usage: nestjs.sh <output_path>}"
mkdir -p "$(dirname "$OUTPUT")"

# Install dependencies
echo "[drift-agent] installing NestJS dependencies..."
if [ -f "pnpm-lock.yaml" ]; then
  pnpm install --frozen-lockfile --prefer-offline 2>/dev/null || pnpm install
elif [ -f "yarn.lock" ]; then
  yarn install --frozen-lockfile 2>/dev/null || yarn install
else
  npm ci 2>/dev/null || npm install
fi

# Rebuild native addons that pnpm may have skipped (e.g. bcrypt)
echo "[drift-agent] rebuilding native modules..."
pnpm rebuild 2>/dev/null || npm rebuild 2>/dev/null || true

# Write the generation script into the project root so Node resolves
# all modules (reflect-metadata, @nestjs/*, bcrypt, etc.) from project node_modules.
cat > ./.drift-nestjs-gen.ts << 'GENEOF'
import 'reflect-metadata';

// ── Mock TypeORM DataSource before any module is loaded ──────────────────────
// This prevents real database connections during swagger generation.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const typeorm = require('typeorm');
const _origInit = typeorm.DataSource.prototype.initialize;
typeorm.DataSource.prototype.initialize = async function (this: any) {
  console.log('[drift-agent] TypeORM DataSource.initialize mocked');
  this.isInitialized = true;
  this.entityMetadatas = this.entityMetadatas ?? [];
  this.migrations = this.migrations ?? [];
  this.subscribers = this.subscribers ?? [];
  this.driver = this.driver ?? { escape: (v: string) => `'${v}'`, options: {} };
  return this;
};
typeorm.DataSource.prototype.getRepository = function () { return { find: async () => [] }; };
typeorm.DataSource.prototype.destroy = async function () { return; };
// ─────────────────────────────────────────────────────────────────────────────

import { NestFactory } from '@nestjs/core';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import * as fs from 'fs';

const OUTPUT = process.env.DRIFT_OUTPUT!;

async function generate() {
  // Use require() with relative paths so ts-node resolves .ts extension correctly
  const candidates = [
    './src/app.module',
    './src/app/app.module',
    './app.module',
    './app/app.module',
  ];

  let AppModule: any;
  for (const p of candidates) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const mod = require(p);
      AppModule = mod.AppModule ?? mod.default?.AppModule;
      if (AppModule) {
        console.log(`[drift-agent] loaded AppModule from ${p}`);
        break;
      }
      console.error(`[drift-agent] ${p} loaded but no AppModule export found`);
    } catch (e: any) {
      console.error(`[drift-agent] failed to import ${p}: ${e.message}`);
    }
  }

  if (!AppModule) {
    console.error('[drift-agent] AppModule not found in any candidate path');
    process.exit(1);
  }

  let app: any;
  try {
    app = await NestFactory.create(AppModule, { logger: ['error'] });
  } catch (e: any) {
    console.error(`[drift-agent] NestFactory.create error: ${e.message}`);
    process.exit(1);
  }

  const config = new DocumentBuilder()
    .setTitle('API')
    .setVersion('1.0')
    .build();
  const doc = SwaggerModule.createDocument(app, config);
  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
  fs.writeFileSync(OUTPUT, JSON.stringify(doc, null, 2));
  console.log(`[drift-agent] generated NestJS OpenAPI schema → ${OUTPUT}`);
  await app.close().catch(() => {});
}

generate().catch(e => {
  console.error('[drift-agent] generation failed:', e.message);
  process.exit(1);
});
GENEOF

DRIFT_OUTPUT="$OUTPUT" npx ts-node \
  --project tsconfig.json \
  --transpile-only \
  ./.drift-nestjs-gen.ts

EXIT_CODE=$?
rm -f ./.drift-nestjs-gen.ts

if [ $EXIT_CODE -ne 0 ]; then
  echo "::error::NestJS schema generation failed. Check logs above for the specific import error." >&2
  exit 1
fi
