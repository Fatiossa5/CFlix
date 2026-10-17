import test from 'node:test';
import assert from 'node:assert/strict';
import {seekStep, qualitySources, restorePosition} from '../public/player-core.js';

test('seek moves ten seconds in either direction and respects video boundaries', () => {
  assert.equal(seekStep(40, 100, 1, null, 0).target, 50);
  assert.equal(seekStep(40, 100, -1, null, 0).target, 30);
  assert.equal(seekStep(95, 100, 1, null, 0).target, 100);
  assert.equal(seekStep(4, 100, -1, null, 0).target, 0);
});

test('rapid same-direction seeks accumulate feedback using actual distance', () => {
  const first = seekStep(40, 100, 1, null, 1000);
  const second = seekStep(first.target, 100, 1, first, 1200);
  const third = seekStep(second.target, 100, 1, second, 1400);
  assert.equal(third.target, 70);
  assert.equal(third.total, 30);
  const nearEnd = seekStep(95, 100, 1, third, 1500);
  assert.equal(nearEnd.total, 35);
});

test('seek feedback resets on direction change and after the burst interval', () => {
  const previous = seekStep(40, 100, 1, null, 1000);
  assert.equal(seekStep(50, 100, -1, previous, 1100).total, 10);
  assert.equal(seekStep(50, 100, 1, previous, 1900).total, 10);
});

test('seek skips videos without a finite positive duration or position', () => {
  for (const duration of [0, -1, NaN, Infinity]) {
    assert.equal(seekStep(20, duration, 1, null, 0), null);
  }
  for (const position of [NaN, Infinity]) {
    assert.equal(seekStep(position, 100, 1, null, 0), null);
  }
});

test('quality menu always retains the original source', () => {
  const movie = {video: '/media/' + 'a'.repeat(32)};
  assert.deepEqual(qualitySources(movie), [{label: 'Orijinal', src: movie.video, value: 'original'}]);
});

test('quality menu uses uploaded variants with distinct selection values', () => {
  const variant = {label: '720p', src: '/media/' + 'b'.repeat(32)};
  const movie = {video: '/media/' + 'a'.repeat(32), qualities: [variant]};
  assert.deepEqual(qualitySources(movie), [
    {label: 'Orijinal', src: movie.video, value: 'original'}, {...variant, value: '720p'},
  ]);
  assert.deepEqual(movie.qualities, [variant]);
});

test('quality menu filters untrusted URLs, unsupported labels and duplicate labels', () => {
  const valid = {label: '1080p', src: '/media/' + 'a'.repeat(32)};
  const result = qualitySources({video: '/original.mp4', qualities: [
    {label: '720p', src: 'https://untrusted.example/video.mp4'},
    {label: '4K', src: '/media/' + 'a'.repeat(32)},
    {label: '480p', src: '/media/not-an-asset'},
    valid, {...valid, src: '/media/' + 'b'.repeat(32)},
  ]});
  assert.equal(result.length, 2);
  assert.equal(result[1].src, valid.src);
  assert.equal(result[1].value, '1080p');
});

test('switching quality preserves an ordinary position without scaling by duration', () => {
  assert.equal(restorePosition(143.25, 300), 143.25);
  assert.equal(restorePosition(143.25, 600), 143.25);
});

test('shorter variants restore just before the end to avoid immediately ending', () => {
  assert.equal(restorePosition(240, 120), 119.95);
  assert.equal(restorePosition(-10, 120), 0);
  assert.equal(restorePosition(10, 0.02), 0);
});

test('position restoration safely handles unavailable variant duration', () => {
  for (const duration of [NaN, Infinity, 0, -1]) {
    assert.equal(restorePosition(120, duration), 0);
  }
});
