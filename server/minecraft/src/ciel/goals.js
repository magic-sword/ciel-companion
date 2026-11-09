// Minecraft内の計画・段の実行・修復。外側の受付と状態はdocs/game-work-contract-ja.md。
// 会話サーバーは段の中身を知らない。段は {kind, args, label, progress} で、ここが作り、ここが動かし、ここが確かめる。
import { ja, shortWhy, WHY_FAILED } from './words.js';

// 決まった直し方（計画し直す）で直る理由
const REPLAN_REASONS = ['missing_materials', 'needs_tool', 'cannot_harvest', 'no_table'];

export function stepLabel(kind, item, count) {
  const n = count > 1 ? ` ${count} 個` : '';   // 「オークの原木を 3 個集める」
  if (kind === 'gather') return `${ja(item)}を${n}集める`;
  if (kind === 'craft') return `${ja(item)}を${n}作る`;
  return `${ja(item)}を${n}手に入れる`;
}

// 体の計画（goal-plan.js の steps）を、目的の係の段にする
export function stepsFrom(planned) {
  return planned.map((p) => {
    const kind = p.kind, item = p.item, count = Number(p.count ?? 1) || 1;
    const args = { item, count };
    if (kind === 'mind') args.text = stepLabel('mind', item, count);
    return { kind, args, label: stepLabel(kind, item, count), progress: kind === 'gather' ? [0, count] : null };
  });
}

export const findStep = (item) => ({ kind: 'find', args: { item, how: 'auto' }, label: `${ja(item)}を探す`, progress: null });

// 段を体の技にする：[技, 引数]。動かせない段なら null
export function skillFor(step) {
  const a = step.args ?? {};
  if (step.kind === 'gather') {
    const got = (step.progress ?? [0, a.count])[0];
    return ['collect', { block: a.item, count: Math.max(1, a.count - got) }];
  }
  if (step.kind === 'craft') return ['craft', { item: a.item, count: a.count }];
  if (step.kind === 'find') return ['find', { block: a.item, how: a.how ?? 'auto' }];
  return null;
}

// 技の結果（体の done）を、段の結果にする。complete と progress で、できたかを会話サーバーに伝える
export function stepResult(step, done) {
  let r = { ...done };
  const a = step.args ?? {};
  const note = r.note ?? {};
  const got0 = step.kind === 'gather' ? (step.progress ?? [0, a.count])[0] : 0;
  if (r.ok && note.short) {   // 頼んだ数に届かなかった
    r = { ...r, ok: false, reason: note.short };
  } else if (r.ok && step.kind === 'gather' && Number(note.gained?.[a.item] ?? 0) < Math.max(1, a.count - got0)) {
    // 体は数え終えたが、この物は足りない（体が別の物も数えた）：近くにもう無い扱いで、探す段から続ける
    r = { ...r, ok: false, reason: 'not_found' };
  }
  if (step.kind === 'gather') {
    const got = Math.min(got0 + Number(note.gained?.[a.item] ?? 0), a.count);
    r.progress = [got, a.count];
    r.complete = got >= a.count;
  } else {
    r.progress = step.progress ?? null;
    r.complete = Boolean(r.ok);
  }
  if (!r.ok && r.reason) r.why_short = WHY_FAILED[r.reason] ? shortWhy(r.reason, note) : WHY_FAILED.error;
  return r;
}

const sameLabels = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

// 決まった直し方。{steps, text} か null（直せない：心に相談）。plan は (item, count) → {steps} か {error}
export function repair({ spec, step, result, remaining }, plan) {
  const reason = result?.reason;
  // 集める物が見える所に無い：先に探す段を足す（探しても無ければ、探す段の失敗として心に相談する）
  if (reason === 'not_found' && step.kind === 'gather') {
    return { steps: [findStep(step.args.item), ...remaining], text: `${ja(step.args.item)}が見える所に無いので、探す段を足した` };
  }
  if (!REPLAN_REASONS.includes(reason) || !spec?.make) return null;
  const r = plan(spec.make, Number(spec.count ?? 1) || 1);
  if (r.error || !r.steps?.length) return null;
  const steps = stepsFrom(r.steps);
  // 計画し直しても同じ：直ったことにしない（同じ計画を 3 回くり返した。2026-11-07）
  if (sameLabels(steps.map((s) => s.label), remaining.map((s) => s.label))) return null;
  return { steps, text: `${shortWhy(reason, result?.note ?? {})}ので、計画を直した` };
}
