import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyFocus } from '../app/focus.js';

test('telecom is relevant only near Santo Amaro', () => {
  const item = { title: 'Link dedicado em fibra óptica', description: 'Acesso à internet' };
  assert.equal(classifyFocus({ ...item, municipality_code: '2928604' })?.company, 'Ti.Net');
  assert.equal(classifyFocus({ ...item, municipality_code: '2918407' }), null);
});

test('vehicle monitoring is relevant in both regions', () => {
  for (const municipality_code of ['2928604', '2918407', '2611101']) {
    const result = classifyFocus({ municipality_code, title: 'Rastreamento e monitoramento de frota por GPS' });
    assert.equal(result?.company, 'AutoControl');
    assert.equal(result?.category, 'Monitoramento veicular');
  }
});

test('unrelated tenders and bundled vehicle rental are excluded', () => {
  for (const title of ['Credenciamento para exames de saúde', 'Aquisição de câmeras CFTV', 'Locação de veículos com rastreamento por GPS']) {
    assert.equal(classifyFocus({ municipality_code: '2918407', title }), null);
  }
});
