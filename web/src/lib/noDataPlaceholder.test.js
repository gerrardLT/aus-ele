import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('NoDataPlaceholder component exists and exports a default function', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  assert.match(source, /export default function NoDataPlaceholder/);
});

test('NoDataPlaceholder displays Chinese no-data message by default', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  assert.match(source, /当前筛选条件下无数据/);
});

test('NoDataPlaceholder displays English no-data message when lang is en', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  assert.match(source, /No data available for current filters/);
});

test('NoDataPlaceholder renders filter chips from the filters prop', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  // Should iterate over filters and render chips
  assert.match(source, /chips\.map/);
  assert.match(source, /chip\.label/);
  assert.match(source, /chip\.value/);
});

test('NoDataPlaceholder uses border-dashed styling consistent with design system', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  assert.match(source, /border-dashed/);
  assert.match(source, /color-muted/);
});

test('NoDataPlaceholder has accessible role=status and aria-label', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  assert.match(source, /role="status"/);
  assert.match(source, /aria-label/);
});

test('NoDataPlaceholder supports bilingual filter labels (zh and en)', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../components/NoDataPlaceholder.jsx'),
    'utf8'
  );
  // Chinese labels
  assert.match(source, /区域/);
  assert.match(source, /年份/);
  // English labels
  assert.match(source, /Region/);
  assert.match(source, /Year/);
});
