// The hero card's colour rule. Missing the target is not symmetric: covering
// more often than promised costs a little margin, covering less often means
// the plan was optimistic and someone bought the gap.

import assert from 'node:assert/strict'
import test from 'node:test'

import { gradeShortfall } from '../src/lib/grade.js'

test('covering at or better than target is green, with no label', () => {
  for (const rate of [0, 4.2, 8.5, 9.9, 10]) {
    const g = gradeShortfall(rate, 10)
    assert.equal(g.tone, 'on-target', `${rate}% should be green`)
    assert.equal(g.label, null)
  }
})

test('optimistic by under a point is still green', () => {
  assert.equal(gradeShortfall(10.9, 10).tone, 'on-target')
})

test('optimistic by 1 to 5 points is amber and says by how much', () => {
  assert.deepEqual(gradeShortfall(11.5, 10), {
    tone: 'off-target',
    label: 'slightly optimistic (+1.5 pp)',
    over: 1.5,
  })
  assert.equal(gradeShortfall(11, 10).tone, 'off-target')
  assert.equal(gradeShortfall(15, 10).tone, 'off-target')
})

test('optimistic beyond 5 points is red', () => {
  const g = gradeShortfall(16.2, 10)
  assert.equal(g.tone, 'off-target-bad')
  assert.equal(g.label, 'optimistic (+6.2 pp)')
})

test('being cautious is never flagged, however far from target', () => {
  // 0% shortfall at a 10% target means the plan was very conservative. That
  // costs margin, not money you did not expect to spend, so it stays green.
  const g = gradeShortfall(0, 10)
  assert.equal(g.tone, 'on-target')
  assert.equal(g.label, null)
})

test('the target follows the confidence setting', () => {
  // at 95% confidence the target is 5%, so 8% is a 3pp optimistic miss
  assert.equal(gradeShortfall(8, 5).label, 'slightly optimistic (+3.0 pp)')
  assert.equal(gradeShortfall(5.5, 5).tone, 'on-target')
})

test('missing inputs grade to nothing rather than guessing', () => {
  assert.equal(gradeShortfall(null, 10), null)
  assert.equal(gradeShortfall(11, null), null)
})
