// 経路探索の歩き方の決まり（技 skills.js と、身を守る係 guard.js が使う）
import pathfinderPkg from 'mineflayer-pathfinder';

const { Movements } = pathfinderPkg;

// 歩くときの決まり：ブロックを壊さない・置かない（持ち主の建物を崩したり、土を積んだりしない）
export function carefulMovements(bot) {
  const m = new Movements(bot);
  m.canDig = false;
  m.allow1by1towers = false;
  m.scafoldingBlocks = [];
  return m;
}

// 集めるときの決まり：掘ってよい（mineflayer-collectblock は、掘る前に canDig を見て、だめなら黙って飛ばす）。積みはしない
export function diggingMovements(bot) {
  const m = carefulMovements(bot);
  m.canDig = true;
  return m;
}
