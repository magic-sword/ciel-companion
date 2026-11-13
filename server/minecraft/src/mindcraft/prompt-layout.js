// Reorder Mindcraft's conversing template for prompt caching without changing its wording.
// Lines whose placeholders are fixed for a bound session ($NAME, $COMMAND_DOCS) and plain
// instruction lines go first; lines with per-turn placeholders ($SELF_PROMPT, $MEMORY,
// $STATS, $INVENTORY, $EXAMPLES, ...) and the closing line follow in their original order.
const FIXED = new Set(['$NAME', '$COMMAND_DOCS']);
const placeholders = line => line.match(/\$[A-Z_]+/g) ?? [];

export function cacheLayout(template) {
  if (typeof template !== 'string' || template.split('$COMMAND_DOCS').length !== 2)
    throw new Error('Mindcraft conversing template must contain $COMMAND_DOCS once');
  // A leading per-turn placeholder shares a line with fixed text upstream ("$SELF_PROMPT Be ...").
  const lines = template.split('\n').flatMap(line => {
    const lead = line.match(/^(\$[A-Z_]+) (.+)$/);
    return lead && !FIXED.has(lead[1]) && placeholders(lead[2]).every(p => FIXED.has(p))
      ? [lead[1], lead[2]] : [line];
  });
  const dynamic = line => placeholders(line).some(p => !FIXED.has(p));
  const lastDynamic = lines.findLastIndex(dynamic);
  const fixed = [], varying = [];
  lines.forEach((line, i) => (dynamic(line) || i > lastDynamic ? varying : fixed).push(line));
  const reference = fixed.join('\n');
  return { reference, template: `${reference}\n${varying.join('\n')}` };
}
