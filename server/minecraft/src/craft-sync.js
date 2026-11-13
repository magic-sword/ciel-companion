// Mineflayer 4.39.0 predicts the crafting output locally before putAway(0).
// Read the server's actual window first; an output must exist on the server.
// This covers crafting-table windows and the player's own 2x2 grid (bot.inventory),
// which has no open window and would otherwise keep phantom outputs in the inventory.
export function confirmedCrafting(bot) {
  if(bot.__confirmedCrafting)return;
  if(typeof bot.putAway!=='function')return;
  const tableWindow=window=>window?.type?.startsWith('minecraft:crafting');
  // The window whose crafting output putAway(0)/clicks refer to, or null outside crafting.
  const craftingWindow=()=>{
    const window=bot.currentWindow;
    if(tableWindow(window))return window;
    return !window&&bot.__handCrafting?bot.inventory:null;
  };
  const sync=async window=>{
    if(typeof bot._syncWindow!=='function')throw new Error('craft_sync_unavailable');
    await bot._syncWindow(window);
  };
  if(typeof bot.craft==='function'){
    const craft=bot.craft.bind(bot);
    bot.craft=async(recipe,count,craftingTable)=>{
      bot.__handCrafting=!craftingTable;
      try {
        const result=await craft(recipe,count,craftingTable);
        // Mineflayer resyncs a table window before closing it, but not the 2x2 grid.
        if(!craftingTable)await sync(bot.inventory);
        return result;
      } finally { bot.__handCrafting=false; }
    };
  }
  if(typeof bot.clickWindow==='function'){
    const click=bot.clickWindow.bind(bot);
    bot.clickWindow=async(...args)=>{
      const window=craftingWindow();
      const result=await click(...args);
      if(window){
        if(tableWindow(window)&&bot.currentWindow!==window)throw new Error('craft_window_changed');
        await sync(window);
      }
      return result;
    };
  }
  const putAway=bot.putAway.bind(bot);
  bot.putAway=async(slot)=>{
    const window=craftingWindow();
    if(slot===0&&window){
      await sync(window);
      if(!window.slots?.[0]){
        bot.__craftEvidence={slots:window.slots?.slice(0,10).map(item=>item?{name:item.name,count:item.count}:null),
          cursor:window.selectedItem?{name:window.selectedItem.name,count:window.selectedItem.count}:null};
        throw new Error('craft_output_unverified');
      }
    }
    return putAway(slot);
  };
  bot.__confirmedCrafting=true;
}
