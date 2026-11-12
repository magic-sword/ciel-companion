import { containsCommand, executeCommand, getCommandDocs, parseCommandMessage } from '../vendor/mindcraft/src/agent/commands/index.js';
import { actionsList } from '../vendor/mindcraft/src/agent/commands/actions.js';
import { queryList } from '../vendor/mindcraft/src/agent/commands/queries.js';
import { readFileSync } from 'node:fs';
import { getInventoryCounts, getNearbyBlockTypes } from '../vendor/mindcraft/src/agent/library/world.js';
import { getDetailedCraftingPlan } from '../vendor/mindcraft/src/utils/mcdata.js';

const goalPrompt = readFileSync(new URL('./prompts/goal.md', import.meta.url), 'utf8');
const actionPrompt = readFileSync(new URL('./prompts/action.md', import.meta.url), 'utf8');

const allowed = new Set(['!stop', '!stats', '!inventory', '!nearbyBlocks', '!entities', '!collectBlocks',
  '!craftRecipe', '!smeltItem', '!searchForBlock', '!searchForEntity', '!goToCoordinates', '!moveAway',
  '!equip', '!consume', '!clearFurnace', '!goToSurface', '!getCraftingPlan', '!craftable']);

function commandDocs(agent) {
  agent.blocked_actions = [...actionsList, ...queryList].map(command => command.name).filter(name => !allowed.has(name));
  return getCommandDocs(agent);
}

export async function resolveItemGoal(runner, request) {
  const bot = runner.bot;
  const response = await runner.coreModel.sendRequest([{role:'user',content:JSON.stringify({request,
    inventory:getInventoryCounts(bot),nearby_blocks:getNearbyBlockTypes(bot),position:bot.entity.position})}],
    commandDocs(runner.agent) + '\n' + goalPrompt, 'json');
  const goal = JSON.parse(response.trim().replace(/^```(?:json)?\s*|\s*```$/g, ''));
  if (typeof goal.clarification === 'string') return {clarification:goal.clarification.slice(0,200)};
  if (!bot.registry.itemsByName[goal.item] || !Number.isInteger(goal.quantity) || goal.quantity<1 || goal.quantity>64
      || !['gain','inventory_target'].includes(goal.quantity_mode) || !['nearby','search'].includes(goal.resource_scope)
      || !['ask','stop'].includes(goal.failure_policy) || typeof goal.command !== 'string')
    throw new Error('Invalid Mindcraft goal');
  return goal;
}

export async function pursueItem(runner, c, target, firstCommand = '') {
  const agent = runner.agent, bot = runner.bot;
  const docs = commandDocs(agent) + '\n' + actionPrompt;
  const turns = [];
  let failures = 0;
  const count = () => bot.inventory.items().filter(i => i.name === c.args.item).reduce((n, i) => n + i.count, 0);
  while (!c.token.cancelled && count() < target) {
    await runner.waitModes();
    if (c.token.cancelled) break;
    const inventory = {};
    for (const item of bot.inventory.items()) inventory[item.name] = (inventory[item.name] ?? 0) + item.count;
    const p = bot.entity.position;
    // Reuse Mindcraft's recipe analysis as observation, without a second CIEL planner.
    let crafting_plan;
    try { crafting_plan = getDetailedCraftingPlan(c.args.item,target,inventory).slice(0,6000); }
    catch { crafting_plan = 'Recipe analysis unavailable; inspect command results.'; }
    turns.push({role:'user',content:JSON.stringify({goal:{item:c.args.item,inventory_target:target,
      resource_scope:c.args.resource_scope},inventory,crafting_plan,nearby_blocks:getNearbyBlockTypes(bot),position:{x:p.x,y:p.y,z:p.z}})});
    runner.activity(c,'thinking');
    const response = firstCommand || await runner.coreModel.sendRequest(turns.slice(-16), docs);
    firstCommand = '';
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
    if(command==='!stop') {
      const error=new Error('not_found');error.goalReason='not_found';throw error;
    }
    runner.activity(c,'executing',command);
    const result = await executeCommand(agent, response);
    turns.push({role:'user',content:JSON.stringify({execution_result:result ?? '',inventory_count:count()})});
    failures = 0;
  }
}
