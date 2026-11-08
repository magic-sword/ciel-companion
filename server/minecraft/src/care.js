// 体の手入れ：おなかが減ったら、持っている食べ物を自分で食べる。docs/minecraft-design-ja.md の 4.2。
// 体の空き時間だけ食べる。命令や防御と装備を奪い合わない。

const EVERY_MS = 2000;
const HUNGRY = 14;        // 空腹（0〜20）がこれ以下なら食べる
const HURT_HEALTH = 14;   // 体力がこれ以下で、空腹が満タンでなければ食べる（体力は空腹が 18 以上で戻る）
// 食べると具合が悪くなるもの・食べるとどこかへ飛ぶもの・とっておくもの
const AVOID = new Set(['rotten_flesh', 'spider_eye', 'poisonous_potato', 'pufferfish', 'suspicious_stew',
  'chorus_fruit', 'golden_apple', 'enchanted_golden_apple', 'chicken']);

// 食べる物（いちばんおなかがふくれるもの）か null
export function pickFood(items, foodsByName, food, health) {
  if (food >= 20 || (food > HUNGRY && health > HURT_HEALTH)) return null;
  return items
    .filter((i) => foodsByName[i.name] && !AVOID.has(i.name))
    .sort((a, b) => foodsByName[b.name].foodPoints - foodsByName[a.name].foodPoints)[0] ?? null;
}

export class Care {
  constructor(report, guard) {
    this.report = report;
    this.guard = guard;
    this.bot = null;
    this._eating = false;
    this._timer = null;
    this.body = null;
  }

  attach(bot) {
    this.detach();
    this.bot = bot;
    if (bot) this._timer = setInterval(() => this._tick(), EVERY_MS);
  }

  detach() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    this.bot = null;
  }

  async _tick() {
    const bot = this.bot;
    if (!bot?.entity || this._eating || this.guard?.active || bot.health <= 0) return;
    const item = pickFood(bot.inventory.items(), bot.registry.foodsByName, bot.food, bot.health);
    if (!item) return;
    this._eating = true;
    try {
      const eat = async () => {
        await bot.equip(item, 'hand');
        if (this.bot !== bot || this.guard?.active) return;
        await bot.consume();
        this.report('event', { kind: 'ate', name: item.name, food: bot.food });
      };
      if (this.body) await this.body.maintain(eat);
      else await eat();
    } catch {
      // 食べている途中で叩かれた・持ち替えた。次の見回りでまた試す
    } finally {
      this._eating = false;
    }
  }
}
