package local.ciel;

import com.google.gson.Gson;
import java.nio.file.*;
import java.util.*;
import net.kyori.adventure.text.Component;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.command.*;
import org.bukkit.entity.Player;
import org.bukkit.event.*;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.*;
import org.bukkit.inventory.*;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.RayTraceResult;

/** Only the configured owner can publish selections; no world editing or model calls. */
public final class PointingPlugin extends JavaPlugin implements Listener {
    private final List<Map<String,Object>> selections = new ArrayList<>();
    private final Gson gson = new Gson();
    private final String session = UUID.randomUUID().toString();
    private String owner;
    private NamespacedKey key;
    private Path output;
    private long lastClick;
    private boolean gazeMode;
    private Map<String,Object> gaze;
    private Map<String,Object> presence;
    private static final long TTL = 60000;

    @Override public void onEnable() {
        owner = System.getenv().getOrDefault("CIEL_POINTING_OWNER", "");
        key = new NamespacedKey(this, "pointer");
        output = Path.of("/data/ciel-pointing/selection.json");
        getServer().getPluginManager().registerEvents(this, this);
        publish();
        getServer().getScheduler().runTaskTimer(this, () -> {
            long now = System.currentTimeMillis();
            if (selections.removeIf(s -> (long)s.get("expires_at") <= now)) publish();
            Player p = getServer().getPlayerExact(owner);
            if (gazeMode) { updateGaze(p); publish(); }
            if (p != null && !selections.isEmpty()) preview(p, selections.getLast());
            else if(p != null && gaze != null) preview(p,gaze);
        }, 5, 5);
    }
    @Override public void onDisable() { selections.clear(); gaze=null; presence=null; publish(); }
    private boolean allowed(Player p) { return !owner.isBlank() && p.getName().equals(owner); }
    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player p) || !allowed(p)) return true;
        if(args.length>0 && (args[0].equals("gaze") || args[0].equals("clear"))) {
            gazeMode=args[0].equals("gaze"); selections.clear(); gaze=null; presence=null; publish();
            p.sendActionBar(Component.text(gazeMode ? "目線指定を開始しました。対象を見ながら話しかけてください。" : "対象の選択を解除しました。"));
            return true;
        }
        ItemStack wand = new ItemStack(Material.BLAZE_ROD);
        var meta = wand.getItemMeta();
        meta.displayName(Component.text("シエルへの指示棒"));
        meta.getPersistentDataContainer().set(key, PersistentDataType.BYTE, (byte)1);
        wand.setItemMeta(meta);
        if (p.getInventory().firstEmpty() < 0) p.sendMessage(Component.text("持ち物に空きを作ってください。"));
        else p.getInventory().addItem(wand);
        return true;
    }
    @EventHandler public void interact(PlayerInteractEvent e) {
        Player p = e.getPlayer();
        ItemStack item = e.getItem();
        if (!allowed(p) || e.getHand() != EquipmentSlot.HAND || item == null ||
            !item.getItemMeta().getPersistentDataContainer().has(key, PersistentDataType.BYTE)) return;
        e.setCancelled(true); // A selection never opens a workbench or breaks/places a block.
        if (e.getAction() != Action.RIGHT_CLICK_AIR && e.getAction() != Action.RIGHT_CLICK_BLOCK) return;
        long now = System.currentTimeMillis();
        if (now - lastClick < 200) return;
        lastClick = now;
        gazeMode=false; gaze=null; presence=null;
        RayTraceResult ray = p.rayTraceBlocks(32, FluidCollisionMode.NEVER);
        if (ray == null || ray.getHitBlock() == null || ray.getHitBlockFace() == null) {
            p.sendActionBar(Component.text("対象がありません。地面やブロックを指してください。")); return;
        }
        Block b = ray.getHitBlock();
        var face = ray.getHitBlockFace();
        Map<String,Object> point = Map.of("x",b.getX(),"y",b.getY(),"z",b.getZ(),
            "block",b.getType().getKey().getKey(),"face",List.of(face.getModX(),face.getModY(),face.getModZ()));
        List<Object> points = new ArrayList<>();
        if (p.isSneaking() && !selections.isEmpty()) {
            var previous = selections.getLast();
            if ((long)previous.get("expires_at") > now && previous.get("world").equals(b.getWorld().getUID().toString()))
                points.add(((List<?>)previous.get("points")).getFirst());
        }
        if (p.isSneaking() && points.isEmpty()) {
            p.sendActionBar(Component.text("まず、しゃがまずに始点を選んでください。")); return;
        }
        points.add(point);
        String dimension = switch(b.getWorld().getEnvironment()) {
            case NORMAL -> "overworld"; case NETHER -> "the_nether"; case THE_END -> "the_end"; default -> "unsupported";
        };
        var selection = new LinkedHashMap<String,Object>();
        selection.put("id",UUID.randomUUID().toString()); selection.put("owner",owner);
        selection.put("player_uuid",p.getUniqueId().toString()); selection.put("world",b.getWorld().getUID().toString());
        selection.put("dimension",dimension); selection.put("created_at",now); selection.put("expires_at",now+TTL);
        selection.put("points",points);
        selections.add(selection);
        while(selections.size()>8) selections.removeFirst();
        publish(); preview(p,selection);
        p.sendActionBar(Component.text(points.size()==1 ? "始点を選びました。話しかけるか、しゃがんで終点を選んでください。" : "範囲を選びました。シエルへ作業を伝えてください。"));
    }
    @EventHandler public void quit(PlayerQuitEvent e) { invalidate(e.getPlayer()); }
    @EventHandler public void world(PlayerChangedWorldEvent e) { invalidate(e.getPlayer()); }
    private void invalidate(Player p) { if (allowed(p)) { selections.clear(); gaze=null; presence=null; publish(); } }
    private void updateGaze(Player p) {
        if(p==null) { gaze=null; presence=null; return; }
        presence=Map.of("world",p.getWorld().getUID().toString(),"player_uuid",p.getUniqueId().toString());
        RayTraceResult ray=p.rayTraceBlocks(32,FluidCollisionMode.NEVER);
        if(ray==null || ray.getHitBlock()==null || ray.getHitBlockFace()==null) { gaze=null; return; }
        Block b=ray.getHitBlock(); var f=ray.getHitBlockFace();
        Map<String,Object> point=Map.of("x",b.getX(),"y",b.getY(),"z",b.getZ(),"block",b.getType().getKey().getKey(),
            "face",List.of(f.getModX(),f.getModY(),f.getModZ()));
        String id=gaze!=null && gaze.get("points").equals(List.of(point)) ? (String)gaze.get("id") : UUID.randomUUID().toString();
        String dimension=switch(b.getWorld().getEnvironment()) {
            case NORMAL -> "overworld"; case NETHER -> "the_nether"; case THE_END -> "the_end"; default -> "unsupported";
        };
        long now=System.currentTimeMillis();
        gaze=new LinkedHashMap<>();
        gaze.put("id",id); gaze.put("owner",owner); gaze.put("player_uuid",p.getUniqueId().toString());
        gaze.put("world",p.getWorld().getUID().toString()); gaze.put("dimension",dimension);
        gaze.put("created_at",now); gaze.put("expires_at",now+1500); gaze.put("points",List.of(point));
    }
    @SuppressWarnings("unchecked") private void preview(Player p, Map<String,Object> selection) {
        if (!selection.get("world").equals(p.getWorld().getUID().toString())) return;
        List<Map<String,Object>> points = (List<Map<String,Object>>)selection.get("points");
        for (var v : points) p.spawnParticle(Particle.END_ROD, new Location(p.getWorld(),
            ((Number)v.get("x")).doubleValue()+.5, ((Number)v.get("y")).doubleValue()+1.1,
            ((Number)v.get("z")).doubleValue()+.5), 3, .2, .1, .2, 0);
        if(points.size()!=2) return;
        var a=points.getFirst(); var b=points.getLast();
        int x1=Math.min((int)a.get("x"),(int)b.get("x")), x2=Math.max((int)a.get("x"),(int)b.get("x"))+1;
        int z1=Math.min((int)a.get("z"),(int)b.get("z")), z2=Math.max((int)a.get("z"),(int)b.get("z"))+1;
        double y=Math.max((int)a.get("y"),(int)b.get("y"))+1.05;
        if((x2-x1)*(z2-z1)>64) return;
        for(int x=x1;x<=x2;x++) for(int z=z1;z<=z2;z++)
            if(x==x1||x==x2||z==z1||z==z2) p.spawnParticle(Particle.END_ROD,new Location(p.getWorld(),x,y,z),1,0,0,0,0);
    }
    private void publish() {
        try {
            Files.createDirectories(output.getParent());
            Path temp=output.resolveSibling("selection.tmp");
            var data=new LinkedHashMap<String,Object>();
            data.put("version",1); data.put("session",session); data.put("selections",selections);
            data.put("gaze",gaze); data.put("presence",presence); data.put("published_at",System.currentTimeMillis());
            Files.writeString(temp,gson.toJson(data));
            Files.move(temp,output,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        } catch(Exception ex) { getLogger().warning("Cannot publish pointing: "+ex.getClass().getSimpleName()); }
    }
}
