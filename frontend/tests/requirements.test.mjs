import assert from 'node:assert/strict';
import { groupByClient } from '../src/lib/requirements.js';

const jds = [
  { id: 1, client_name: 'Infosys', demand_id: 'java', no_of_positions: 3, status: 'Open' },
  { id: 2, client_name: ' infosys ', demand_id: 'pega', no_of_positions: 2, status: null },
  { id: 3, client_name: 'Infosys', demand_id: 'java', no_of_positions: 5, status: 'Cancelled' },
  { id: 4, client_name: 'Infosys', demand_id: 'java', no_of_positions: null, status: 'Open' },
  { id: 5, client_name: null, demand_id: 'java', no_of_positions: 4, status: 'Fulfilled' },
  { id: 6, client_name: 'Coforge', demand_id: 'java', no_of_positions: 0, status: 'Open' },
];

const groups = groupByClient(jds);
const by = (name) => groups.find((g) => g.name === name);

// Client names differing only by case/whitespace share one folder; the first-seen spelling is kept.
assert.deepEqual(groups.map((g) => g.name), ['Coforge', 'Infosys', '']);
// Positions: cancelled demands and blank/zero positions add nothing.
assert.equal(by('Infosys').positions, 5);
assert.equal(by('Coforge').positions, 0);
assert.equal(by('').positions, 4);
// Demand counts are unchanged and still available for the secondary label.
assert.equal(by('Infosys').items.length - by('Infosys').cancelled, 3);
// The existing `practices` map keeps counting demands.
assert.deepEqual([...by('Infosys').practices.entries()], [['java', 2], ['pega', 1]]);

console.log('requirements tests passed');
