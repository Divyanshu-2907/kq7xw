// Guards the deploy bug this file was written for: a production bundle that
// pointed at http://localhost:8000 and so could never reach the API once
// deployed. Uses the Node test runner, so it needs no extra dependency.
//
// Run with: npm test

import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import test from 'node:test'

import { DEV_API_PORT, resolveApiBase } from '../src/api.js'

const here = dirname(fileURLToPath(import.meta.url))

// Vite sets DEV/PROD on import.meta.env; these mirror the two real builds.
const PRODUCTION = { DEV: false, PROD: true }
const DEVELOPMENT = { DEV: true, PROD: false }

test('the production default is same-origin, not localhost', () => {
  // Even served from localhost, a production build must stay same-origin.
  const base = resolveApiBase(PRODUCTION, { protocol: 'http:', hostname: 'localhost' })
  assert.equal(base, '', 'production must default to a same-origin (empty) base')
  assert.doesNotMatch(
    base,
    /localhost|127\.0\.0\.1|0\.0\.0\.0/,
    'a production bundle must never default to a local address',
  )
})

test('no default base anywhere resolves to a local address', () => {
  // Whatever else changes, this is the invariant that keeps deploys working.
  const loc = { protocol: 'http:', hostname: 'localhost' }
  for (const env of [PRODUCTION, {}, { PROD: true }, { DEV: false }]) {
    assert.doesNotMatch(resolveApiBase(env, loc), /localhost|127\.0\.0\.1/)
  }
})

test('dev points at the backend port on whatever host served the page', () => {
  const asLocalhost = { protocol: 'http:', hostname: 'localhost' }
  assert.equal(resolveApiBase(DEVELOPMENT, asLocalhost), `http://localhost:${DEV_API_PORT}`)

  // Opening the dev server from another device on the network must reach that
  // machine's backend, not the phone's own loopback.
  const overLan = { protocol: 'http:', hostname: '192.168.1.42' }
  assert.equal(resolveApiBase(DEVELOPMENT, overLan), `http://192.168.1.42:${DEV_API_PORT}`)
})

test('dev with no location to work from falls back to same-origin', () => {
  assert.equal(resolveApiBase(DEVELOPMENT, undefined), '')
})

test('an explicit VITE_API_BASE always wins', () => {
  assert.equal(
    resolveApiBase({ ...PRODUCTION, VITE_API_BASE: 'https://api.example.com' }),
    'https://api.example.com',
  )
  assert.equal(
    resolveApiBase({ ...DEVELOPMENT, VITE_API_BASE: 'https://api.example.com' }),
    'https://api.example.com',
  )
})

test('an explicit empty VITE_API_BASE means same-origin, not "fall back"', () => {
  // This is what the Docker build passes; `??` would keep it, `||` would not.
  const loc = { protocol: 'http:', hostname: 'localhost' }
  assert.equal(resolveApiBase({ ...DEVELOPMENT, VITE_API_BASE: '' }, loc), '')
})

test('a trailing slash is trimmed so paths do not double up', () => {
  assert.equal(
    resolveApiBase({ ...PRODUCTION, VITE_API_BASE: 'https://api.example.com/' }),
    'https://api.example.com',
  )
})

test('the built bundle contains no local address', (t) => {
  // The unit tests above can pass while a hard-coded URL elsewhere still ships,
  // so check the real artefact.
  const dist = join(here, '..', 'dist', 'assets')
  if (!existsSync(dist)) {
    // Report as skipped, not passed. Returning early here would make this a
    // silent no-op if the build step were ever moved after the test step, and
    // the regression it guards would sail through green.
    t.skip('no dist/ to inspect — run `npm run build` first')
    return
  }

  const bundles = readdirSync(dist).filter((f) => f.endsWith('.js'))
  assert.ok(bundles.length > 0, 'expected at least one built bundle to check')

  for (const name of bundles) {
    const text = readFileSync(join(dist, name), 'utf8')
    assert.ok(
      !/localhost:\d+|127\.0\.0\.1:\d+/.test(text),
      `${name} contains a local address`,
    )
  }
})
