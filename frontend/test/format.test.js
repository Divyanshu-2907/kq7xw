// Display units. The charts and the hero card speak GW; the cards speak MW.
// Getting a factor of 1000 wrong here is the kind of mistake nobody notices
// until a trader does.

import assert from 'node:assert/strict'
import test from 'node:test'

import { GW, MW, signedGW, signedMW, pct } from '../src/lib/format.js'

test('GW converts from MW and always carries its unit', () => {
  assert.equal(GW(7021.5), '7.0 GW')
  assert.equal(GW(7021.5, 2), '7.02 GW')
  assert.equal(GW(0), '0.0 GW')
})

test('MW keeps megawatts, grouped, with its unit', () => {
  assert.equal(MW(1947.4), '1,947 MW')
  assert.equal(MW(-138.5), '-139 MW')
})

test('signed forms keep the direction visible', () => {
  assert.equal(signedGW(1373), '+1.4 GW')
  assert.equal(signedGW(-1373), '-1.4 GW')
  assert.equal(signedMW(1373.2), '+1,373 MW')
})

test('missing values render as a dash, never as zero', () => {
  for (const blank of [null, undefined, NaN]) {
    assert.equal(GW(blank), '—')
    assert.equal(MW(blank), '—')
    assert.equal(signedGW(blank), '—')
    assert.equal(pct(blank), '—')
  }
})

test('a GW figure is a thousandth of the MW figure', () => {
  // The scale is what matters. Exact halves round differently between
  // toFixed and toLocaleString, so allow one unit of the last shown digit
  // rather than pinning a rounding mode.
  for (const mw of [9059.5, 1947.4, 20942, 0]) {
    const asGw = Number(GW(mw, 3).replace(' GW', ''))
    assert.ok(
      Math.abs(asGw - mw / 1000) < 0.001,
      `GW(${mw}) gave ${asGw}, expected about ${mw / 1000}`,
    )
  }
})
