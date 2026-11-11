// Mineflayer 4.39.0 predicts the crafting output locally before putAway(0).
// Read the server's actual window first; an output must exist on the server.
export function confirmedCrafting(bot) {
  if(bot.__confirmedCrafting)return;
  if(typeof bot.putAway!=='function')return;
  if(typeof bot.clickWindow==='function'){
    const click=bot.clickWindow.bind(bot);
    bot.clickWindow=async(...args)=>{
      const window=bot.currentWindow;
      const result=await click(...args);
      if(window?.type?.startsWith('minecraft:crafting')){
        if(bot.currentWindow!==window)throw new Error('craft_window_changed');
        if(typeof bot._syncWindow!=='function')throw new Error('craft_sync_unavailable');
        await bot._syncWindow(window);
      }
      return result;
    };
  }
  const putAway=bot.putAway.bind(bot);
  bot.putAway=async(slot)=>{
    const window=bot.currentWindow;
    if(slot===0&&window?.type?.startsWith('minecraft:crafting')){
      if(typeof bot._syncWindow!=='function')throw new Error('craft_sync_unavailable');
      await bot._syncWindow(window);
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
