// A stationary fixture actor. Only the privileged scorer changes its position.
import mineflayer from 'mineflayer';
const bot = mineflayer.createBot({ host: '127.0.0.1', port: 25566, version: '1.21.11',
  username: 'Bench_Owner', auth: 'offline', hideErrors: true });
bot.on('error', error => { console.error(error.code ?? error.name); process.exitCode = 1; });
bot.on('end', () => process.exit(process.exitCode ?? 0));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => bot.quit());
