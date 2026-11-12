import { AsyncLocalStorage } from 'node:async_hooks';

// Upstream cooperative interrupts do not cover every await. Prevent a late continuation
// from issuing new physical operations after stop or after a mode took ownership.
export class ActionScope {
  constructor(bot) {
    this.storage = new AsyncLocalStorage();
    this.active = null;
    this.operations = new Set();
    const install = (object, name, asynchronous, cleanup = () => false) => {
      if (typeof object?.[name] !== 'function') return;
      const original = object[name].bind(object);
      object[name] = (...args) => {
        const context = this.storage.getStore();
        if (context?.cancelled && !cleanup(...args)) {
          if (!asynchronous) return;
          return Promise.reject(new Error('interrupted'));
        }
        const result = original(...args);
        if (!context || !result?.then) return result;
        const pending = Promise.resolve(result);
        this.operations.add(pending);
        void pending.then(() => this.operations.delete(pending), () => this.operations.delete(pending));
        return pending;
      };
    };
    for (const name of ['dig', 'placeBlock', 'equip', 'craft', 'consume', 'toss', 'tossStack',
      'activateBlock', 'activateEntity', 'openChest', 'openFurnace', 'lookAt', 'look']) install(bot, name, true);
    for (const name of ['attack', 'activateItem', 'setControlState']) install(bot, name, false);
    install(bot.pathfinder, 'goto', true);
    install(bot.pathfinder, 'setGoal', false, goal => goal === null);
    install(bot.pvp, 'attack', false);
    install(bot.collectBlock, 'collect', true);
  }

  run(fn) {
    const context = { cancelled: false };
    this.active = context;
    return this.storage.run(context, fn);
  }

  interrupt() { if (this.active) this.active.cancelled = true; }

  async settle() {
    while (this.operations.size) await Promise.allSettled([...this.operations]);
  }
}
