import focusRules from './focus_rules.json' with { type: 'json' };

export function normalize(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function matchingTerms(text, terms) {
  return [...new Set(terms.map(normalize))].filter((term) => {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`).test(text);
  });
}

export function classifyFocus(item) {
  const code = String(item.municipality_code || '');
  const isLocal = focusRules.local_codes.includes(code);
  if (!isLocal && !focusRules.regional_codes.includes(code)) return null;
  const text = normalize(`${item.title || ''} ${item.description || ''}`);
  const vehicle = focusRules.vehicle;
  const vehicleIsBundled = matchingTerms(normalize(item.title), vehicle.unrelated_primary_objects).length > 0;
  const direct = matchingTerms(text, vehicle.direct);
  const context = matchingTerms(text, vehicle.context);
  const signal = matchingTerms(text, vehicle.signal);
  if (!vehicleIsBundled && (direct.length || (context.length && signal.length))) {
    const terms = direct.length ? direct : [...context.slice(0, 2), ...signal.slice(0, 2)];
    return { company: 'AutoControl', category: 'Monitoramento veicular', score: Math.min(100, 75 + 5 * (terms.length - 1)), terms };
  }
  if (!isLocal) return null;
  const categories = Object.entries(focusRules.telecom);
  const matches = categories.map(([key, terms]) => [key, matchingTerms(text, terms)]);
  const allTerms = [...new Set(matches.flatMap(([, terms]) => terms))];
  if (!allTerms.length) return null;
  const strongest = matches.reduce((best, entry) => entry[1].length > best[1].length ? entry : best);
  const labels = { fiber: 'Fibra & FTTH', internet: 'Links & Internet', network: 'Redes & Wi-Fi', telephony: 'Telefonia IP' };
  return { company: 'Ti.Net', category: labels[strongest[0]], score: Math.min(100, 65 + 7 * (allTerms.length - 1)), terms: allTerms };
}
