// Vanilla's 0.6F width is rounded to float before conversion to double.
// Using 0.3 places the client slightly inside walls; Paper 1.21.11 then
// rejects jumps and repeatedly corrects the position (mineflayer#3911).
export function alignPlayerCollision(bot) {
  if (bot.physics) bot.physics.playerHalfWidth = Math.fround(0.6) / 2;
}
