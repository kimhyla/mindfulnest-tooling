#!/usr/bin/env python3
"""Rule 7 Path B preflight 133: bidirectional video<->waveform play/pause/seek sync.

After preflight 132, WaveSurfer owns its own audio (from ws.load) and the video
element has its own audio track (from the rendered Preview MP4). They have
SEPARATE play buttons and play INDEPENDENTLY. Kim reports: they drift out of sync.

This patch installs bidirectional event coordination:
  - Video play/pause/seek -> mirror to WaveSurfer
  - WaveSurfer play/pause/interaction -> mirror to video
  - Single `syncing` flag suppresses the reflection-back to prevent infinite loops
  - Video is MUTED (WS provides audible audio via ws.load; video is visual-only)
  - No setMediaElement binding -- the preflight-123/126 seek-reset loop cannot recur
    because ws.media and pl are SEPARATE elements; sync is purely event-driven

Counter-gamma tightened patcher contract: anchor uniqueness, overlap guard,
32-URI base64 integrity, atomic rename, idempotency probe.
"""
from __future__ import annotations
import hashlib, os, re, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
BACKUP_DIR = PROJECT_ROOT / "Production" / "Event_1" / ".storyboard_backups"
LD_BEGIN = "<!-- BEGIN LD V3 Phase B/A Authoring Panels"
LD_END = "<!-- END LD V3 Phase B/A Authoring Panels"
BACKUP_KEEP = 10

IDEMPOTENCY_TOKENS = ["preflight 133: video<->ws sync"]

# Anchor: the end of installPlayButton from preflight 132 (unique token).
# Inject a new installVideoWsSync function right after it. Also call
# installVideoWsSync from tryMountWaveSurfer at the same point where
# installPlayButton is called.

# ---- Edit A: Inject installVideoWsSync function definition ----
# Anchor: the closing of installPlayButton function. Use its unique signature.
EDIT_A_OLD = """    ws.on("finish", function(){ btn.textContent = "\u25B6 Play audio"; });
    waveEl.parentNode.insertBefore(btn, waveEl);
  }"""
EDIT_A_NEW = """    ws.on("finish", function(){ btn.textContent = "\u25B6 Play audio"; });
    waveEl.parentNode.insertBefore(btn, waveEl);
  }

  // preflight 133: video<->ws sync -- bidirectional play/pause/seek mirroring.
  // Video is visual-only (muted); WaveSurfer is the audible audio source.
  // syncing flag prevents infinite reflection (event ping-pong).
  function installVideoWsSync(phase) {
    var ws = window["__phase_"+phase+"_ws"];
    var pl = $("phase-"+phase+"-preview-player");
    if (!ws || !pl) return;
    if (pl.dataset.mnP133SyncInstalled === "1") return;
    pl.dataset.mnP133SyncInstalled = "1";

    // Mute video: WS provides audible audio via ws.load. Video is visual only.
    // Without this, user hears two audio streams with slight phase offset (echo).
    pl.muted = true;

    var syncing = false;

    // Video events -> WS
    pl.addEventListener("play", function() {
      if (syncing) return;
      syncing = true;
      try {
        if (ws.isPlaying && !ws.isPlaying()) {
          // Sync position first, then play
          var d = ws.getDuration(); if (d > 0 && pl.duration > 0) {
            try { ws.seekTo(Math.min(1, pl.currentTime / pl.duration)); } catch(_){}
          }
          ws.play();
        }
      } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });
    pl.addEventListener("pause", function() {
      if (syncing) return;
      syncing = true;
      try { if (ws.isPlaying && ws.isPlaying()) ws.pause(); } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });
    pl.addEventListener("seeked", function() {
      if (syncing) return;
      syncing = true;
      try {
        var d = ws.getDuration();
        if (d > 0 && pl.duration > 0) ws.seekTo(Math.min(1, pl.currentTime / pl.duration));
      } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });

    // WS events -> Video
    ws.on("play", function() {
      if (syncing) return;
      syncing = true;
      try {
        if (pl.src && pl.readyState >= 2 && pl.paused) {
          // Sync position first
          try { pl.currentTime = ws.getCurrentTime(); } catch(_){}
          var p = pl.play(); if (p && p.catch) p.catch(function(){});
        }
      } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });
    ws.on("pause", function() {
      if (syncing) return;
      syncing = true;
      try { if (pl.src && !pl.paused) pl.pause(); } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });
    ws.on("interaction", function() {
      // interaction fires on click/drag scrub; emits currentTime in seconds
      if (syncing) return;
      syncing = true;
      try {
        if (pl.src && pl.readyState >= 1 && ws.getCurrentTime) {
          pl.currentTime = ws.getCurrentTime();
        }
      } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });
    ws.on("finish", function() {
      if (syncing) return;
      syncing = true;
      try { if (pl.src && !pl.paused) pl.pause(); } catch(_) {}
      finally { setTimeout(function(){ syncing = false; }, 50); }
    });

    console.log("[MN p133] video<->ws sync installed for phase="+phase);
  }"""
EDIT_A_VERIFY = "preflight 133: video<->ws sync"

# ---- Edit B: Call installVideoWsSync from tryMountWaveSurfer (next to installPlayButton) ----
EDIT_B_OLD = """      // preflight 132: installPlayButton after WS is live. ws.on("ready")
      // ensures the play button only fires playPause when audio is decoded.
      try { ws.on("ready", function(){ installPlayButton(phase); }); } catch(_){}
      // Also install immediately in case "ready" already fired (cache hit).
      try { installPlayButton(phase); } catch(_){}"""
EDIT_B_NEW = """      // preflight 132: installPlayButton after WS is live. ws.on("ready")
      // ensures the play button only fires playPause when audio is decoded.
      try { ws.on("ready", function(){ installPlayButton(phase); installVideoWsSync(phase); }); } catch(_){}
      // Also install immediately in case "ready" already fired (cache hit).
      try { installPlayButton(phase); } catch(_){}
      // preflight 133: install video<->ws sync. Safe to call before video is loaded
      // (listeners attach to pl; they fire only when pl events happen).
      try { installVideoWsSync(phase); } catch(_){}"""
EDIT_B_VERIFY = "preflight 133: install video<->ws sync"

EDITS = [
    # (tag, old, new, verify_token, allow_overlap)
    ("A_installVideoWsSync", EDIT_A_OLD, EDIT_A_NEW, EDIT_A_VERIFY, True),   # append-style
    ("B_wire_into_mount",    EDIT_B_OLD, EDIT_B_NEW, EDIT_B_VERIFY, True),   # extend existing block
]

B64_RE = re.compile(r'data:(?:image|audio|video|application)/[a-zA-Z0-9+.\-]+;base64,[A-Za-z0-9+/=]+')

def sha256_b(d): return hashlib.sha256(d).hexdigest()
def extract_b64(t): return [(m.group(0).split(",",1)[0], sha256_b(m.group(0).encode("ascii"))) for m in B64_RE.finditer(t)]
def locate_ld(t):
    a = t.find(LD_BEGIN); b = t.find(LD_END)
    if a < 0 or b < 0: raise RuntimeError("sentinels missing")
    return a, b + len(LD_END)
def atomic_write(p, data):
    with tempfile.NamedTemporaryFile(dir=str(p.parent), prefix=p.name+".tmp_", delete=False) as f:
        f.write(data); f.flush(); os.fsync(f.fileno()); tmp = Path(f.name)
    os.replace(str(tmp), str(p))
def prune():
    baks = sorted(BACKUP_DIR.glob("*.bak_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for o in baks[BACKUP_KEEP:]:
        try: o.unlink()
        except OSError: pass

def main():
    dry = "--dry-run" in sys.argv
    raw = TARGET.read_bytes()
    txt = raw.decode("utf-8")
    print(f"Target: {TARGET}\n  size: {len(raw):,}  pre-SHA: {sha256_b(raw)[:16]}...")

    hits = [t for t in IDEMPOTENCY_TOKENS if t in txt]
    if len(hits) == len(IDEMPOTENCY_TOKENS): print("  IDEMPOTENT: already applied"); return 0

    ld_a, ld_b = locate_ld(txt); ld = txt[ld_a:ld_b]
    pre_b64 = extract_b64(txt); print(f"  base64 URIs: {len(pre_b64)}")

    for tag, old, new, tok, allow_overlap in EDITS:
        if ld.count(old) != 1: print(f"ANCHOR FAIL [{tag}]: region-count={ld.count(old)}", file=sys.stderr); return 3
        if txt.count(old) != ld.count(old): print(f"SCOPE FAIL [{tag}]", file=sys.stderr); return 3
        if (not allow_overlap) and (old in new): print(f"OVERLAP FAIL [{tag}]", file=sys.stderr); return 3
    print(f"  anchors verified: {len(EDITS)}")

    patched = txt
    for tag, old, new, tok, allow_overlap in EDITS:
        if patched.count(old) != 1: print(f"DRIFT [{tag}]", file=sys.stderr); return 4
        patched = patched.replace(old, new, 1)
        print(f"  edit {tag}: {len(new)-len(old):+d} chars")

    post_b64 = extract_b64(patched)
    if post_b64 != pre_b64: print("BASE64 DRIFT", file=sys.stderr); return 5
    print(f"  base64: {len(post_b64)}/{len(pre_b64)} identical")
    for tag, old, new, tok, allow_overlap in EDITS:
        if tok not in patched: print(f"TOKEN MISSING [{tag}]", file=sys.stderr); return 6

    if dry: print(f"\n[DRY RUN] delta: {len(patched.encode('utf-8'))-len(raw):+d} bytes"); return 0

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = BACKUP_DIR / f"{TARGET.name}.bak_preflight133_video_ws_sync_{ts}"
    bak.write_bytes(raw); print(f"  backup: {bak.name}")
    atomic_write(TARGET, patched.encode("utf-8"))
    print(f"  post-SHA: {sha256_b(TARGET.read_bytes())[:16]}...")
    prune()
    print("\n--- PREFLIGHT 133 APPLIED ---")
    return 0

if __name__ == "__main__":
    sys.exit(main())
