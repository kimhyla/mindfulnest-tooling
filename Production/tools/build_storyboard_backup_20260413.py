#!/usr/bin/env python3
"""
MindfulNest Storyboard Builder
===============================
Generates a self-contained HTML storyboard from images, audio, and dialogue data.
The output HTML has editable text, play buttons, image assignment, pause sliders,
reorder, and an export button.

REGISTRY-FIRST WORKFLOW (PREFERRED):
    Use build_storyboard_from_registry(module_id, event_number, lines, output_path, title, subtitle)
    This queries the Directus prod_visual_assets registry to ensure all images are approved
    and registered, maintaining pipeline integrity.

    from build_storyboard import build_storyboard_from_registry
    build_storyboard_from_registry(
        module_id="M1",
        event_number=1,
        lines=[{"speaker":"Guide Bird","text":"Hello!","image":"master","audio_key":None,"pause":0.5,"section":"Setup"}],
        output_path="storyboard.html",
        title="Event 1: First Meeting",
        subtitle="Arc 1 Storyboard"
    )

LEGACY WORKFLOW (MANUAL CONFIG — FALLBACK ONLY):
    python3 build_storyboard.py --config storyboard_config.json --output storyboard.html

CONFIG FORMAT (JSON):
{
  "title": "Event 1: Tessa's Fall",
  "subtitle": "MindfulNest Arc 1 / M1 Story Scene",
  "images": {
    "master": "/path/to/master.png",
    "tessa_closeup": "/path/to/tessa_closeup.png",
    "guidebird_face": "/path/to/guidebird_face.png"
  },
  "image_labels": {
    "master": "Master Wide Shot",
    "tessa_closeup": "Tessa Close-up",
    "guidebird_face": "Guide Bird Face"
  },
  "audio": {
    "shot6_s1": "/path/to/shot6_s1.mp3",
    "shot6_s2": "/path/to/shot6_s2.mp3"
  },
  "speakers": ["Guide Bird", "Tessa", "Luna", "[Stage Direction]", "[Narration]"],
  "lines": [
    {"speaker": "Guide Bird", "text": "Are you OK?", "image": "master", "audio_key": null, "pause": 0.5, "section": "Setup"},
    {"speaker": "Tessa", "text": "I fell...", "image": "tessa_closeup", "audio_key": "shot6_s1", "pause": 0.3, "section": "Setup"}
  ]
}

OR call build_storyboard() directly from Python:

    from build_storyboard import build_storyboard
    build_storyboard(config_dict, output_path)
"""

import argparse
import base64
import io
import json
import os
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def query_registry_images(module_id, event_number):
    """
    Query the MindfulNest Directus prod_visual_assets registry for approved images.

    MANDATORY ENTRY POINT: This function enforces the registry-first workflow.
    All storyboard builds should begin by querying the registry to ensure consistency
    with the production pipeline.

    Args:
        module_id: str, e.g. "M1" or "arc1_m1_event1"
        event_number: int, e.g. 1 (for Event 1)

    Returns:
        dict of {asset_name: {"path": file_path, "label": asset_name, "dimensions": [w,h], "type": asset_type}}
        Returns empty dict if query fails or no approved assets found.

    Raises:
        ImportError: if requests library is not available
        Exception: detailed error on auth or API failure
    """
    if not HAS_REQUESTS:
        raise ImportError(
            "requests library required for Directus queries. "
            "Install: pip install requests"
        )

    DIRECTUS_BASE = "https://directus-production-3460.up.railway.app"
    EMAIL = "kimhyla11@gmail.com"
    PASSWORD = "directus11"

    try:
        # Authenticate
        auth_url = f"{DIRECTUS_BASE}/auth/login"
        auth_payload = {"email": EMAIL, "password": PASSWORD}
        auth_resp = requests.post(auth_url, json=auth_payload, timeout=10)
        auth_resp.raise_for_status()
        token = auth_resp.json().get("data", {}).get("access_token")

        if not token:
            raise ValueError("No access token returned from Directus auth")

        # Query approved visual assets
        query_url = (
            f"{DIRECTUS_BASE}/items/prod_visual_assets"
            f"?filter[module_id][_eq]={module_id}"
            f"&filter[status][_eq]=approved"
            f"&filter[event_number][_eq]={event_number}"
        )
        headers = {"Authorization": f"Bearer {token}"}
        query_resp = requests.get(query_url, headers=headers, timeout=10)
        query_resp.raise_for_status()

        items = query_resp.json().get("data", [])

        # Build asset dict
        result = {}
        for item in items:
            asset_name = item.get("asset_name", "unnamed")
            result[asset_name] = {
                "path": item.get("file_path", ""),
                "label": item.get("display_label", asset_name),
                "dimensions": [item.get("width"), item.get("height")] if item.get("width") else None,
                "type": item.get("asset_type", "unknown")
            }

        print(f"Registry query: found {len(result)} approved assets for {module_id} event {event_number}")
        return result

    except Exception as e:
        print(f"ERROR: Registry query failed for {module_id} event {event_number}: {e}")
        raise


def build_storyboard_from_registry(module_id, event_number, lines, output_path, title="", subtitle=""):
    """
    Build a storyboard by querying the Directus registry for approved images.

    PREFERRED ENTRY POINT: This function should be called instead of manually
    constructing config dicts. It ensures all images are registered and approved
    before inclusion in the storyboard, maintaining pipeline integrity.

    Args:
        module_id: str, e.g. "M1" or "arc1_m1_event1"
        event_number: int, e.g. 1
        lines: list of line dicts (same format as build_storyboard config["lines"])
               Each line should have: speaker, text, image, audio_key (optional), pause, section
        output_path: where to write the HTML
        title: storyboard title (default: "Storyboard")
        subtitle: storyboard subtitle (default: "")

    Returns:
        output_path (str) on success

    Raises:
        ImportError: if requests library not available
        Exception: if registry query fails
    """
    # Query registry
    registry_assets = query_registry_images(module_id, event_number)

    if not registry_assets:
        raise ValueError(
            f"No approved images found in registry for {module_id} event {event_number}. "
            "Ensure images are uploaded and marked status=approved before building."
        )

    # Build image config from registry
    images = {}
    image_labels = {}
    for asset_name, asset_data in registry_assets.items():
        images[asset_name] = asset_data["path"]
        image_labels[asset_name] = asset_data["label"]

    # Build full config dict
    config = {
        "title": title or f"Module {module_id} – Event {event_number}",
        "subtitle": subtitle,
        "images": images,
        "image_labels": image_labels,
        "audio": {},  # Populated from lines
        "speakers": list(set(line.get("speaker", "Character") for line in lines)),
        "lines": lines
    }

    # Extract audio references from lines
    for line in lines:
        if line.get("audio_key") and line["audio_key"] not in config["audio"]:
            # Audio paths should be provided in the config; registry query doesn't fetch audio
            # This is a placeholder — caller must provide audio paths if available
            config["audio"][line["audio_key"]] = ""

    print(f"Building storyboard from registry: {len(images)} images, {len(lines)} lines")
    return build_storyboard(config, output_path)


def encode_image(path, thumb_size=80, ref_size=200):
    """Encode an image as base64, creating thumbnail and reference versions."""
    if HAS_PIL:
        img = Image.open(path)
        # Thumbnail
        t = img.copy()
        t.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        buf = io.BytesIO()
        t.save(buf, format="PNG", optimize=True)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode()
        # Reference (larger for grid display)
        r = img.copy()
        r.thumbnail((ref_size, ref_size), Image.LANCZOS)
        buf2 = io.BytesIO()
        r.save(buf2, format="PNG", optimize=True)
        ref_b64 = base64.b64encode(buf2.getvalue()).decode()
    else:
        # Without PIL, encode full image (larger file but still works)
        with open(path, "rb") as f:
            full_b64 = base64.b64encode(f.read()).decode()
        thumb_b64 = full_b64
        ref_b64 = full_b64
    return thumb_b64, ref_b64


def encode_audio(path):
    """Encode an audio file as base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def build_storyboard(config, output_path):
    """
    Build a self-contained HTML storyboard from a config dict.

    WARNING: This is a LOW-LEVEL function. For production work, use
    build_storyboard_from_registry() instead. That function queries the
    Directus registry to ensure all images are approved and registered.
    Manual config should only be used as a fallback for testing or offline work.

    Args:
        config: dict with keys: title, subtitle, images, image_labels, audio, speakers, lines
        output_path: where to write the HTML file
    """
    # Emit warning if config was constructed manually (no registry query)
    if not config.get("_registry_validated"):
        print(
            "⚠️  WARNING: build_storyboard() called without registry validation. "
            "For production, use build_storyboard_from_registry(module_id, event_number, ...) "
            "to ensure images are registered and approved in Directus."
        )

    title = config.get("title", "Storyboard")
    subtitle = config.get("subtitle", "")
    speakers = config.get("speakers", ["Character A", "Character B", "[Stage Direction]"])
    image_labels = config.get("image_labels", {})
    image_labels["none"] = "(No image)"

    # Encode images
    thumbs = {}
    refs = {}
    for key, path in config.get("images", {}).items():
        if os.path.exists(path):
            thumbs[key], refs[key] = encode_image(path)
            print(f"  Image: {key} ({os.path.getsize(path)//1024}KB -> thumb {len(thumbs[key])//1024}KB)")
        else:
            print(f"  WARNING: Image not found: {path}")

    # Encode audio
    audio_data = {}
    for key, path in config.get("audio", {}).items():
        if os.path.exists(path):
            audio_data[key] = encode_audio(path)
            print(f"  Audio: {key} ({os.path.getsize(path)//1024}KB)")
        else:
            print(f"  WARNING: Audio not found: {path}")

    # Build HTML
    parts = []

    # ===== HEAD + CSS =====
    parts.append(f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a1a2e;color:#eee;padding:20px}}
h1{{text-align:center;color:#e0c3fc;margin-bottom:3px;font-size:1.4em}}
.sub{{text-align:center;color:#888;margin-bottom:8px;font-size:.85em}}
.inst{{text-align:center;color:#aaa;font-size:.8em;margin-bottom:15px;line-height:1.5;max-width:700px;margin-left:auto;margin-right:auto}}
.inst strong{{color:#e0c3fc}}
.bar{{display:flex;gap:8px;justify-content:center;margin-bottom:15px;flex-wrap:wrap}}
.b{{background:#4a3f6b;color:#e0c3fc;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px}}
.b:hover{{background:#6b5b95}}
.b.exp{{background:#2d6a4f;color:#b7e4c7}}
.b.add{{background:#1a4a6e;color:#a5d8ff}}
.sh{{max-width:880px;margin:18px auto 6px;padding:8px 12px;background:#0f3460;border-radius:8px;color:#a5d8ff;font-weight:600;font-size:14px}}
.tl{{max-width:880px;margin:0 auto}}
.lr{{background:#16213e;border-radius:10px;padding:12px;margin-bottom:8px;border:1px solid #333}}
.lr.act{{border-color:#e0c3fc;box-shadow:0 0 12px rgba(224,195,252,.2)}}
.lt{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.ln{{background:#4a3f6b;color:#e0c3fc;min-width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px}}
.ss{{background:#0f3460;color:#ffd6a5;border:1px solid #444;border-radius:6px;padding:4px 6px;font-size:12px;font-weight:600}}
.at{{font-size:11px;color:#666;margin-left:auto}}
.at.h{{color:#40916c}}
.de{{width:100%;background:#0a0a1a;color:#eee;border:1px solid #333;border-radius:6px;padding:8px 10px;font-size:13px;font-family:inherit;resize:vertical;min-height:36px;line-height:1.4}}
.de:focus{{border-color:#e0c3fc;outline:none}}
.de.sd{{color:#888;font-style:italic}}
.lc{{display:flex;align-items:center;gap:12px;margin-top:6px;flex-wrap:wrap}}
.pb{{border:none;width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.pb.green{{background:#2d6a4f;color:#b7e4c7}}
.pb.green:hover{{background:#40916c;transform:scale(1.08)}}
.pb.gray{{background:#333;color:#666;cursor:default}}
.pb.playing{{background:#c06060;color:#fff}}
.th{{width:50px;height:50px;border-radius:6px;object-fit:cover;border:1px solid #444}}
.is select{{background:#0f3460;color:#eee;border:1px solid #444;border-radius:6px;padding:4px;font-size:11px}}
.pc{{display:flex;align-items:center;gap:6px}}
.pc label{{color:#888;font-size:11px}}
.pc input{{width:70px}}
.pv{{color:#e0c3fc;font-size:11px;min-width:28px}}
.ro button{{background:#333;color:#888;border:none;width:22px;height:18px;cursor:pointer;border-radius:3px;font-size:10px;display:block;margin:1px 0}}
.ro button:hover{{background:#555;color:#eee}}
.db{{background:#4a2020;color:#ff8888;border:none;width:22px;height:22px;border-radius:4px;cursor:pointer;font-size:12px}}
.ep{{max-width:880px;margin:15px auto;background:#16213e;border-radius:10px;padding:15px;border:1px solid #333;display:none}}
.ep h3{{color:#b7e4c7;margin-bottom:8px;font-size:14px}}
.ep pre{{background:#0a0a1a;padding:10px;border-radius:8px;color:#ccc;font-size:11px;white-space:pre-wrap;max-height:400px;overflow-y:auto}}
.ig{{max-width:880px;margin:15px auto}}
.ig h3{{color:#e0c3fc;margin-bottom:8px;font-size:13px}}
.gg{{display:flex;gap:8px;flex-wrap:wrap}}
.ic{{text-align:center}}
.ic img{{width:120px;height:120px;object-fit:cover;border-radius:6px;border:2px solid #333}}
.ic p{{color:#888;font-size:10px;margin-top:3px}}
</style></head><body>
<h1>{title}</h1>
<p class="sub">{subtitle}</p>
<div class="inst"><strong>How to use:</strong> Edit dialogue directly in text boxes. Change speakers, reorder, assign images, set pauses.
Click <strong>Export</strong> to lock the sequence. Then we generate TTS from your locked text.<br>
<span style="color:#2d6a4f;font-size:16px">&#9654;</span> Green = has TTS (click to hear) &nbsp;
<span style="color:#666;font-size:16px">&#9711;</span> Gray = no audio yet</div>
<div class="bar">
<button class="b" onclick="playAllAudio()" id="pab">&#9654; Play All (audio lines)</button>
<button class="b" onclick="stopAll()">&#9632; Stop</button>
<button class="b add" onclick="addLine()">+ Add Line</button>
<button class="b exp" onclick="exportSeq()">&#128230; Export Locked Sequence</button>
</div>''')

    # Image reference grid
    parts.append('<div class="ig"><h3>Available Images</h3><div class="gg">')
    for key in config.get("images", {}).keys():
        if key in refs:
            label = image_labels.get(key, key)
            parts.append(f'<div class="ic"><img src="data:image/png;base64,{refs[key]}"><p>{label}</p></div>')
    parts.append('</div></div>')

    parts.append('<div class="tl" id="tl"></div>')
    parts.append('<div class="ep" id="ep"><h3>Locked Sequence &mdash; Copy and paste to Claude</h3>')
    parts.append('<pre id="et"></pre><button class="b" onclick="copyExp()" style="margin-top:8px">Copy to Clipboard</button></div>')

    # ===== JAVASCRIPT =====
    parts.append('<script>')

    # Embed thumbnail data
    parts.append('var TH={};')
    for key, b64 in thumbs.items():
        parts.append(f'TH["{key}"]="data:image/png;base64,{b64}";')

    # Embed audio data
    parts.append('var AU={};')
    for key, b64 in audio_data.items():
        parts.append(f'AU["{key}"]="data:audio/mpeg;base64,{b64}";')

    # Image labels
    labels_json = json.dumps(image_labels)
    parts.append(f'var IN={labels_json};')

    # Speakers
    speakers_json = json.dumps(speakers)
    parts.append(f'var SP={speakers_json};')

    # Lines data
    lines_js = []
    for line in config.get("lines", []):
        s = line.get("speaker", "")
        t = line.get("text", "").replace('"', '\\"').replace("'", "\\'")
        i = line.get("image", "none")
        a = line.get("audio_key")
        p = line.get("pause", 0.5)
        g = line.get("section", "")
        a_str = f'"{a}"' if a else "null"
        lines_js.append(f'{{s:"{s}",t:"{t}",i:"{i}",a:{a_str},p:{p},g:"{g}"}}')
    parts.append("var L=[" + ",\n".join(lines_js) + "];")

    # Core JS engine (no template literals, pure DOM manipulation)
    parts.append('''
var cA=null,paA=false,paI=-1;

function render(){
var c=document.getElementById("tl");c.innerHTML="";var cg="";
for(var i=0;i<L.length;i++){var l=L[i];
if(l.g!==cg){cg=l.g;var h=document.createElement("div");h.className="sh";h.textContent=cg;c.appendChild(h);}
var r=document.createElement("div");r.className="lr";r.id="r"+i;
var ha=l.a&&AU[l.a];var sd=l.s==="[Stage Direction]"||l.s==="[Narration]";
var tp=document.createElement("div");tp.className="lt";
var nm=document.createElement("div");nm.className="ln";nm.textContent=""+(i+1);tp.appendChild(nm);
var sl=document.createElement("select");sl.className="ss";sl.setAttribute("data-i",""+i);
sl.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].s=this.value;render();};
for(var j=0;j<SP.length;j++){var o=document.createElement("option");o.value=SP[j];o.textContent=SP[j];if(SP[j]===l.s)o.selected=true;sl.appendChild(o);}
tp.appendChild(sl);
var tg=document.createElement("span");tg.className="at"+(ha?" h":"");tg.textContent=ha?"(TTS: "+l.a+")":"(no TTS yet)";tp.appendChild(tg);
r.appendChild(tp);
var ta=document.createElement("textarea");ta.className="de"+(sd?" sd":"");ta.value=l.t;
ta.rows=Math.max(1,Math.ceil(l.t.length/80));
ta.setAttribute("data-i",""+i);ta.oninput=function(){L[parseInt(this.getAttribute("data-i"))].t=this.value;};
r.appendChild(ta);
var ct=document.createElement("div");ct.className="lc";
var pb=document.createElement("button");pb.id="pb"+i;
if(ha){pb.className="pb green";pb.innerHTML="&#9654;";pb.title="Play TTS audio";
pb.setAttribute("data-i",""+i);pb.onclick=function(){playLine(parseInt(this.getAttribute("data-i")));};
}else{pb.className="pb gray";pb.innerHTML="&#9711;";pb.title="No audio yet";}
ct.appendChild(pb);
if(l.i!=="none"&&TH[l.i]){var im=document.createElement("img");im.className="th";im.src=TH[l.i];ct.appendChild(im);
}else{var ph=document.createElement("div");ph.style.cssText="width:50px;height:50px;background:#222;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#555;font-size:10px";ph.textContent="none";ct.appendChild(ph);}
var id=document.createElement("div");id.className="is";
var is2=document.createElement("select");is2.setAttribute("data-i",""+i);
is2.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].i=this.value;render();};
var ks=Object.keys(IN);for(var k=0;k<ks.length;k++){var oo=document.createElement("option");oo.value=ks[k];oo.textContent=IN[ks[k]];if(ks[k]===l.i)oo.selected=true;is2.appendChild(oo);}
id.appendChild(is2);ct.appendChild(id);
var pc=document.createElement("div");pc.className="pc";
var pl2=document.createElement("label");pl2.textContent="Pause:";pc.appendChild(pl2);
var ps=document.createElement("input");ps.type="range";ps.min="0";ps.max="3";ps.step="0.1";ps.value=""+l.p;
ps.setAttribute("data-i",""+i);ps.oninput=function(){var x=parseInt(this.getAttribute("data-i"));L[x].p=parseFloat(this.value);document.getElementById("pv"+x).textContent=this.value+"s";};
pc.appendChild(ps);
var pvl=document.createElement("span");pvl.className="pv";pvl.id="pv"+i;pvl.textContent=l.p.toFixed(1)+"s";pc.appendChild(pvl);
ct.appendChild(pc);
var ro=document.createElement("div");ro.className="ro";
var ub=document.createElement("button");ub.innerHTML="&#9650;";ub.setAttribute("data-i",""+i);
ub.onclick=function(){mv(parseInt(this.getAttribute("data-i")),-1);};if(i===0)ub.disabled=true;ro.appendChild(ub);
var dnb=document.createElement("button");dnb.innerHTML="&#9660;";dnb.setAttribute("data-i",""+i);
dnb.onclick=function(){mv(parseInt(this.getAttribute("data-i")),1);};if(i===L.length-1)dnb.disabled=true;ro.appendChild(dnb);
ct.appendChild(ro);
var dl=document.createElement("button");dl.className="db";dl.innerHTML="&#10005;";dl.setAttribute("data-i",""+i);
dl.onclick=function(){var x=parseInt(this.getAttribute("data-i"));if(confirm("Delete line "+(x+1)+"?")){L.splice(x,1);render();}};
ct.appendChild(dl);
r.appendChild(ct);c.appendChild(r);}}

function mv(i,d){var j=i+d;if(j<0||j>=L.length)return;var t=L[i];L[i]=L[j];L[j]=t;render();}
function addLine(){L.push({s:SP[0],t:"(new line)",i:"master",a:null,p:0.5,g:"Custom"});render();window.scrollTo(0,document.body.scrollHeight);}

function playLine(i){
stopAll();var k=L[i].a;if(!k||!AU[k])return;
cA=new Audio(AU[k]);
var b=document.getElementById("pb"+i);var r=document.getElementById("r"+i);
b.className="pb playing";b.innerHTML="&#9632;";r.classList.add("act");
cA.play().catch(function(e){console.error(e);});
cA.onended=function(){b.className="pb green";b.innerHTML="&#9654;";r.classList.remove("act");cA=null;
if(paA&&paI===i){setTimeout(function(){if(!paA)return;var n=i+1;while(n<L.length&&(!L[n].a||!AU[L[n].a]))n++;
if(n<L.length){paI=n;playLine(n);}else{paA=false;document.getElementById("pab").innerHTML="&#9654; Play All (audio lines)";}
},L[i].p*1000);}};}

function playAllAudio(){if(paA){stopAll();return;}paA=true;
var f=-1;for(var i=0;i<L.length;i++){if(L[i].a&&AU[L[i].a]){f=i;break;}}
if(f===-1){alert("No lines have TTS audio yet.");paA=false;return;}
paI=f;document.getElementById("pab").innerHTML="&#9632; Stop";playLine(f);}

function stopAll(){paA=false;paI=-1;if(cA){cA.pause();cA=null;}
var bs=document.querySelectorAll(".pb.playing");for(var i=0;i<bs.length;i++){bs[i].className="pb green";bs[i].innerHTML="&#9654;";}
var rs=document.querySelectorAll(".lr.act");for(var i=0;i<rs.length;i++)rs[i].classList.remove("act");
var p=document.getElementById("pab");if(p)p.innerHTML="&#9654; Play All (audio lines)";}

function exportSeq(){
var ep=document.getElementById("ep");ep.style.display="block";
var t=document.title+" - LOCKED STORYBOARD\\nExported: "+new Date().toLocaleString()+"\\n"+"=".repeat(50)+"\\n\\n";
var cg="";
for(var i=0;i<L.length;i++){var l=L[i];
if(l.g!==cg){cg=l.g;t+="--- "+cg+" ---\\n\\n";}
var im=IN[l.i]||"none";var an=l.a?" [HAS TTS: "+l.a+"]":" [NEEDS TTS]";
if(l.s==="[Stage Direction]"||l.s==="[Narration]"){t+=(i+1)+". "+l.t+"\\n   Image: "+im+" | Pause: "+l.p.toFixed(1)+"s\\n\\n";}
else{t+=(i+1)+". ["+im+"] "+l.s+': "'+l.t+'"\\n   Pause: '+l.p.toFixed(1)+"s"+an+"\\n\\n";}}
var nt=0,ht=0;for(var i=0;i<L.length;i++){if(L[i].a)ht++;else if(L[i].s!=="[Stage Direction]"&&L[i].s!=="[Narration]")nt++;}
t+="\\n--- SUMMARY ---\\nTotal: "+L.length+" | With TTS: "+ht+" | Needs TTS: "+nt+"\\n";
document.getElementById("et").textContent=t;}

function copyExp(){var t=document.getElementById("et").textContent;navigator.clipboard.writeText(t).then(function(){});}

render();
''')
    parts.append('</script></body></html>')

    html = '\n'.join(parts)
    with open(output_path, 'w') as f:
        f.write(html)
    print(f"\nStoryboard written: {output_path} ({len(html)//1024}KB)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build MindfulNest storyboard HTML")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    build_storyboard(config, args.output)


if __name__ == "__main__":
    main()
