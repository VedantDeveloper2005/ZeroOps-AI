import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the actual page parser against the backend's legacy stream format.
const source = readFileSync(new URL('../src/app/dashboard/deployments/page.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const needed = new Set(['isRecord', 'isStageStatus', 'normalizeStageStatus', 'parseDurationSeconds', 'parseEvidenceKind', 'parseRecordedStages']);
const code = ast.statements.filter(node => ts.isFunctionDeclaration(node) && needed.has(node.name?.text)).map(node => node.getText(ast)).join('\n');
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const context = vm.createContext({});
vm.runInContext(compiled, context);

test('numeric stream IDs retain the canonical key used by persisted stage attempts', () => {
  const keys = ['source', 'unit_tests', 'application_deployment', 'health_check'];
  const persisted = keys.map((key, index) => ({ id: `uuid-${index}`, stage_key: key }));
  const streamed = context.parseRecordedStages(keys.map((key, index) => ({ id: index + 1, key, label: key, status: 'queued' })));
  for (const event of streamed) {
    assert.ok(persisted.some(stage => stage.stage_key === event.stage_key), `Stream replay must update ${event.stage_key}, not append a duplicate`);
  }
});

test('normalized keys take precedence while genuinely legacy records keep their ID', () => {
  const result = context.parseRecordedStages([
    { id: 'uuid', stage_key: 'unit_tests', key: 'old-name', name: 'Tests', status: 'running' },
    { id: 9, label: 'Legacy stage', status: 'pending' },
  ]);
  assert.equal(result[0].stage_key, 'unit_tests');
  assert.equal(result[1].stage_key, '9');
  assert.equal(result[1].status, 'queued');
});
