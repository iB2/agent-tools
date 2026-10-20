'use strict';
// Tests run against the demo, or against any voiced deck given as VD_DECK=/abs/path/deck.html.
const fs = require('fs');
const path = require('path');
const lib = require('../../tools/browser/lib');
const PLUGIN = path.resolve(__dirname, '../..');
const DECK = path.resolve(process.env.VD_DECK || path.join(PLUGIN, 'examples/demo/deck.html'));
const ROOT = path.dirname(DECK);
const DEMO = '/' + path.basename(DECK);
const TEMPLATE = path.join(PLUGIN, 'template');

function manifest() {
  const html = fs.readFileSync(DECK, 'utf8');
  const m = html.match(/<script type="application\/json" id="voice">([\s\S]*?)<\/script>/);
  return m ? JSON.parse(m[1].replace(/<\\\//g, '</')) : null;
}

module.exports = { ...lib, PLUGIN, DECK, ROOT, DEMO, TEMPLATE, manifest };
