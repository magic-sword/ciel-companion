package local.ciel;

import com.google.gson.Gson;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.GZIPOutputStream;
import org.bukkit.*;
import org.bukkit.block.*;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.*;
import org.bukkit.event.block.*;
import org.bukkit.event.entity.*;
import org.bukkit.plugin.java.JavaPlugin;

/** Dedicated test instrumentation. Observes blocks; never changes the world. */
final class BenchmarkAudit implements Listener {
    private static final int X1=-48,X2=48,Y1=60,Y2=81,Z1=-48,Z2=48;
    private final JavaPlugin plugin;
    private final Gson gson=new Gson();
    private final Path folder=Path.of("/data/ciel-benchmark-audit");
    private World world;
    private String id;
    private List<String> initial;
    private Map<Integer,String> observed=new HashMap<>();
    private Set<Integer> pending=new HashSet<>();
    private BufferedWriter events;
    private int sequence;
    private String failure="";
    BenchmarkAudit(JavaPlugin p) {
        plugin=p;
        p.getServer().getPluginManager().registerEvents(this,p);
        p.getServer().getScheduler().runTaskTimer(p,this::settle,1,1);
    }
    private int index(int x,int y,int z) {return ((x-X1)*(Y2-Y1+1)+y-Y1)*(Z2-Z1+1)+z-Z1;}
    private boolean inside(Block b) {return world!=null&&b.getWorld().equals(world)&&b.getX()>=X1&&b.getX()<=X2&&b.getY()>=Y1&&b.getY()<=Y2&&b.getZ()>=Z1&&b.getZ()<=Z2;}
    private Block block(int i) {
        int z=i%(Z2-Z1+1)+Z1;i/=Z2-Z1+1;
        int y=i%(Y2-Y1+1)+Y1;int x=i/(Y2-Y1+1)+X1;
        return world.getBlockAt(x,y,z);
    }
    private String value(Block b) {
        String data=b.getBlockData().getAsString();
        if(b.getState() instanceof Container c) {
            StringBuilder out=new StringBuilder(data).append('|');
            for(var item:c.getInventory().getContents())out.append(item==null?"-":Base64.getEncoder().encodeToString(item.serializeAsBytes())).append(';');
            return out.toString();
        }
        return data;
    }
    private List<String> snapshot() {
        var out=new ArrayList<String>((X2-X1+1)*(Y2-Y1+1)*(Z2-Z1+1));
        for(int x=X1;x<=X2;x++)for(int y=Y1;y<=Y2;y++)for(int z=Z1;z<=Z2;z++)out.add(value(world.getBlockAt(x,y,z)));
        return out;
    }
    private String hash(List<String> values)throws Exception {
        var digest=MessageDigest.getInstance("SHA-256");
        for(String s:values){digest.update(s.getBytes(StandardCharsets.UTF_8));digest.update((byte)0);}
        return HexFormat.of().formatHex(digest.digest());
    }
    boolean command(CommandSender sender,String[] args) {
        if(sender instanceof Player||args.length!=2||!args[1].matches("[a-f0-9]{32}"))return false;
        try {
            if(args[0].equals("start")) {
                if(id!=null)throw new IllegalStateException("audit already active");
                world=plugin.getServer().getWorlds().getFirst();
                if(!world.getName().equals("ciel-benchmark"))throw new IllegalStateException("not benchmark world");
                Files.createDirectories(folder);
                id=args[1];sequence=0;failure="";observed.clear();pending.clear();
                initial=snapshot();
                try(var writer=new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(folder.resolve(id+"-initial.json.gz"),StandardOpenOption.CREATE_NEW)),StandardCharsets.UTF_8)) {
                    gson.toJson(Map.of("version",1,"id",id,"bounds",List.of(X1,Y1,Z1,X2,Y2,Z2),"states",initial,"sha256",hash(initial)),writer);
                }
                events=Files.newBufferedWriter(folder.resolve(id+"-events.jsonl"),StandardOpenOption.CREATE_NEW);
                sender.sendMessage("CIEL_AUDIT_STARTED "+id);
            }else if(args[0].equals("finish")&&args[1].equals(id)) {
                settle();events.flush();events.close();events=null;
                var last=snapshot();var changes=new ArrayList<Map<String,Object>>();
                for(int i=0;i<last.size();i++)if(!last.get(i).equals(initial.get(i))) {
                    Block b=block(i);changes.add(Map.of("position",List.of(b.getX(),b.getY(),b.getZ()),"before",initial.get(i),"after",last.get(i)));
                }
                Files.writeString(folder.resolve(id+"-final.json"),gson.toJson(Map.of("version",1,"id",id,"sequence",sequence,
                    "complete",failure.isEmpty(),"error",failure,"changes",changes,"initial_sha256",hash(initial),"final_sha256",hash(last))));
                sender.sendMessage("CIEL_AUDIT_FINISHED "+id);id=null;initial=null;world=null;observed.clear();pending.clear();
            }else return false;
            return true;
        }catch(Exception e){failure=e.getClass().getSimpleName();sender.sendMessage("CIEL_AUDIT_ERROR "+failure);return true;}
    }
    private void write(Block b,String cause,String actor,String before,String after) {
        if(events==null||!inside(b))return;
        if(sequence>=50000){failure="event_limit";return;}
        try {
            events.write(gson.toJson(Map.of("id",id,"sequence",++sequence,"tick",Bukkit.getCurrentTick(),"time_ms",System.currentTimeMillis(),
                "position",List.of(b.getX(),b.getY(),b.getZ()),"cause",cause,"actor",actor,"before",before,"after",after)));
            events.newLine();events.flush();
        }catch(IOException e){failure="event_write_failed";}
    }
    private void mark(Block b) {if(inside(b))pending.add(index(b.getX(),b.getY(),b.getZ()));}
    private void accepted(Block b,String cause,String after) {if(inside(b)){write(b,cause,"server",value(b),after);mark(b);}}
    private void settle() {
        if(events==null)return;
        var batch=new HashSet<>(pending);pending.clear();
        for(int i:batch) {
            Block b=block(i);String before=observed.getOrDefault(i,initial.get(i)),after=value(b);
            if(!before.equals(after))write(b,"physics","server",before,after);
            observed.put(i,after);
        }
    }
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void broken(BlockBreakEvent e) {
        Block b=e.getBlock();if(!inside(b))return;
        write(b,"break",e.getPlayer().getName(),value(b),"minecraft:air");
        observed.put(index(b.getX(),b.getY(),b.getZ()),"minecraft:air");mark(b);
    }
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void placed(BlockPlaceEvent e) {
        Block b=e.getBlockPlaced();if(!inside(b))return;
        String after=value(b);write(b,"place",e.getPlayer().getName(),e.getBlockReplacedState().getBlockData().getAsString(),after);
        observed.put(index(b.getX(),b.getY(),b.getZ()),after);mark(b);
    }
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void physics(BlockPhysicsEvent e) {
        Block b=e.getBlock();mark(b);
        for(var face:new org.bukkit.block.BlockFace[]{org.bukkit.block.BlockFace.UP,org.bukkit.block.BlockFace.DOWN,org.bukkit.block.BlockFace.NORTH,org.bukkit.block.BlockFace.SOUTH,org.bukkit.block.BlockFace.EAST,org.bukkit.block.BlockFace.WEST})mark(b.getRelative(face));
    }
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void flow(BlockFromToEvent e){accepted(e.getToBlock(),"flow",e.getBlock().getBlockData().getAsString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void entity(EntityChangeBlockEvent e){accepted(e.getBlock(),"entity_change",e.getTo().getKey().toString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void form(BlockFormEvent e){accepted(e.getBlock(),"form",e.getNewState().getBlockData().getAsString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void spread(BlockSpreadEvent e){accepted(e.getBlock(),"spread",e.getNewState().getBlockData().getAsString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void grow(BlockGrowEvent e){accepted(e.getBlock(),"grow",e.getNewState().getBlockData().getAsString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void fade(BlockFadeEvent e){accepted(e.getBlock(),"fade",e.getNewState().getBlockData().getAsString());}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void burn(BlockBurnEvent e){accepted(e.getBlock(),"burn","minecraft:air");}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void decay(LeavesDecayEvent e){accepted(e.getBlock(),"decay","minecraft:air");}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void explode(EntityExplodeEvent e){for(Block b:e.blockList())accepted(b,"entity_explode","minecraft:air");}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void blockExplode(BlockExplodeEvent e){for(Block b:e.blockList())accepted(b,"block_explode","minecraft:air");}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void piston(BlockPistonExtendEvent e){for(Block b:e.getBlocks()){accepted(b,"piston","pending");accepted(b.getRelative(e.getDirection()),"piston","pending");}}
    @EventHandler(priority=EventPriority.MONITOR,ignoreCancelled=true) public void retract(BlockPistonRetractEvent e){for(Block b:e.getBlocks()){accepted(b,"piston","pending");accepted(b.getRelative(e.getDirection()),"piston","pending");}}
}
