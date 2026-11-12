import { containsCommand, executeCommand, getCommandDocs, parseCommandMessage } from '../vendor/mindcraft/src/agent/commands/index.js';
import { actionsList } from '../vendor/mindcraft/src/agent/commands/actions.js';
import { queryList } from '../vendor/mindcraft/src/agent/commands/queries.js';

const allowed = new Set(['!stats', '!inventory', '!nearbyBlocks', '!nearbyEntities', '!collectBlocks',
  '!craftRecipe', '!smeltItem', '!searchForBlock', '!searchForEntity', '!goToCoordinates', '!moveAway',
  '!equip', '!consume', '!clearFurnace', '!goToSurface']);

export async function pursueItem(runner, c, target) {
  const agent = runner.agent, bot = runner.bot;
  agent.blocked_actions = [...actionsList, ...queryList].map(command => command.name).filter(name => !allowed.has(name));
  const docs = getCommandDocs(agent);
  const turns = [];
  let failures = 0;
  const count = () => bot.inventory.items().filter(i => i.name === c.args.item).reduce((n, i) => n + i.count, 0);
  while (!c.token.cancelled && count() < target) {
    await runner.waitModes();
    if (c.token.cancelled) break;
    const inventory = Object.fromEntries(bot.inventory.items().map(i => [i.name, i.count]));
    const p = bot.entity.position;
    turns.push({role:'user',content:JSON.stringify({goal:{item:c.args.item,inventory_target:target,
      resource_scope:c.args.resource_scope},inventory,position:{x:p.x,y:p.y,z:p.z}})});
    const response = await runner.coreModel.sendRequest(turns.slice(-16), docs);
    if(c.token.cancelled) break;
    turns.push({role:'assistant',content:response});
    const command = containsCommand(response);
    if (!command || !allowed.has(command)) {
      if (++failures >= 3) throw new Error('Mindcraft did not select an executable command');
      continue;
    }
    if(c.args.resource_scope === 'nearby' && ['!searchForBlock','!searchForEntity','!goToCoordinates','!moveAway','!goToSurface'].includes(command))
      throw new Error('Requested exploration exceeds nearby resource scope');
    const parsed = parseCommandMessage(response);
    if(typeof parsed === 'string') { turns.push({role:'user',content:parsed}); continue; }
    const result = await executeCommand(agent, response);
    turns.push({role:'user',content:JSON.stringify({execution_result:result ?? '',inventory_count:count()})});
    failures = 0;
  }
}
