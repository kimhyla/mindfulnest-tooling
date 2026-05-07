#!/usr/bin/env python3
"""
MindfulNest TTS Review Tool Builder
====================================
Generates a self-contained HTML TTS review interface for post-generation dialogue review.
After voice stems are rendered from a locked storyboard, this tool lets Kim:
1. Listen to each line's TTS audio
2. See the text sent to ElevenLabs
3. Edit text if pronunciation/delivery needs tweaking
4. Mark each line as Approved or Needs Regeneration
5. Export a review manifest (approved lines + lines needing regen with updated text)

USAGE:
    python3 build_tts_review.py --config tts_review_config.json --output tts_review.html

CONFIG FORMAT (JSON):
{
  "title": "Event 1: Tessa's Fall — TTS Review",
  "event_id": "m1_event_1",
  "lines": [
    {
      "id": "line_001",
      "speaker": "Guide Bird",
      "text": "Are you OK?",
      "audio_path": "/path/to/guidebird_001.mp3",
      "image_key": "master",
      "takes": {}
    },
    {
      "id": "line_002",
      "speaker": "Tessa",
      "text": "I fell...",
      "audio_path": "/path/to/tessa_001.mp3",
      "image_key": "tessa_closeup",
      "takes": {"v2": "/path/to/tessa_001_v2.mp3"}
    }
  ],
  "images": {
    "master": "/path/to/master.png",
    "tessa_closeup": "/path/to/tessa_closeup.png"
  }
}

OR call build_tts_review() directly from Python:

    from build_tts_review import build_tts_review
    build_tts_review(config_dict, output_path)
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


def encode_image(path, thumb_size=80):
    """Encode an image as base64 thumbnail."""
    if HAS_PIL:
        img = Image.open(path)
        t = img.copy()
        t.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        buf = io.BytesIO()
        t.save(buf, format="PNG", optimize=True)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode()
    else:
        with open(path, "rb") as f:
            thumb_b64 = base64.b64encode(f.read()).decode()
    return thumb_b64


def encode_audio(path):
    """Encode an audio file as base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def build_tts_review(config, output_path):
    """
    Build a self-contained HTML TTS review tool from a config dict.

    Args:
        config: dict with keys: title, event_id, lines, images
        output_path: where to write the HTML file
    """
    title = config.get("title", "TTS Review")
    event_id = config.get("event_id", "event_unknown")

    # Encode images
    thumbs = {}
    for key, path in config.get("images", {}).items():
        if os.path.exists(path):
            thumbs[key] = encode_image(path)
            print(f"  Image: {key} ({os.path.getsize(path)//1024}KB)")
        else:
            print(f"  WARNING: Image not found: {path}")

    # Encode audio (primary takes + alternative takes)
    audio_data = {}
    for line in config.get("lines", []):
        line_id = line.get("id", "unknown")
        audio_path = line.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            key = f"audio_{line_id}"
            audio_data[key] = encode_audio(audio_path)
            print(f"  Audio: {key} ({os.path.getsize(audio_path)//1024}KB)")
        # Alternative takes
        takes = line.get("takes", {})
        for take_name, take_path in takes.items():
            if take_path and os.path.exists(take_path):
                take_key = f"audio_{line_id}_{take_name}"
                audio_data[take_key] = encode_audio(take_path)
                print(f"  Audio: {take_key} ({os.path.getsize(take_path)//1024}KB)")

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
.b{{background:#4a3f6b;color:#e0c3fc;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500}}
.b:hover{{background:#6b5b95}}
.b.exp{{background:#2d6a4f;color:#b7e4c7;font-weight:600}}
.b.exp:hover{{background:#40916c}}
.b.app{{background:#1a4a6e;color:#a5d8ff;font-weight:600}}
.b.app:hover{{background:#2a6a9e}}
.tl{{max-width:900px;margin:0 auto}}
.cd{{background:#16213e;border-radius:10px;padding:14px;margin-bottom:10px;border:1px solid #333}}
.cd.pending{{border-color:#776622}}
.cd.approved{{border-color:#2d6a4f;box-shadow:0 0 8px rgba(45,106,79,.15)}}
.cd.regen{{border-color:#6a3030;box-shadow:0 0 8px rgba(106,48,48,.15)}}
.hd{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.ln{{background:#4a3f6b;color:#e0c3fc;min-width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px}}
.sp{{background:#0f3460;color:#ffd6a5;border:1px solid #444;border-radius:6px;padding:4px 8px;font-size:12px;font-weight:600}}
.sbb{{display:flex;gap:6px;margin-left:auto;align-items:center}}
.stat{{border-radius:20px;padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;user-select:none;border:1px solid #555;transition:all 0.2s}}
.stat.pending{{background:#776622;color:#fff;border-color:#997733}}
.stat.pending:hover{{background:#997733}}
.stat.approved{{background:#2d6a4f;color:#b7e4c7;border-color:#40916c}}
.stat.approved:hover{{background:#40916c}}
.stat.regen{{background:#6a3030;color:#ff9999;border-color:#994444}}
.stat.regen:hover{{background:#994444}}
.body{{margin-top:8px}}
.txt{{width:100%;background:#0a0a1a;color:#eee;border:1px solid #333;border-radius:6px;padding:10px;font-size:13px;font-family:monospace;resize:vertical;min-height:44px;line-height:1.4}}
.txt:focus{{border-color:#e0c3fc;outline:none}}
.txt.orig{{color:#999;background:#0a0a1a;border-color:#333}}
.ctrls{{display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap}}
.pb{{border:none;width:44px;height:44px;border-radius:50%;cursor:pointer;font-size:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s}}
.pb.green{{background:#2d6a4f;color:#b7e4c7}}
.pb.green:hover{{background:#40916c;transform:scale(1.08)}}
.pb.gray{{background:#333;color:#666;cursor:default}}
.pb.playing{{background:#c06060;color:#fff;animation:pulse 0.5s infinite}}
@keyframes pulse{{0%{{opacity:1}}50%{{opacity:0.7}}100%{{opacity:1}}}}
.th{{width:50px;height:50px;border-radius:6px;object-fit:cover;border:1px solid #444;flex-shrink:0}}
.thp{{display:flex;align-items:center;gap:6px;font-size:11px;color:#888}}
.comp{{background:#1a4a6e;color:#a5d8ff;border:1px solid #2a6a9e;padding:6px 10px;border-radius:6px;font-size:11px;cursor:pointer}}
.comp:hover{{background:#2a6a9e}}
.compm{{margin-top:8px;padding:10px;background:#0f3460;border-radius:6px;border:1px solid #333;font-size:11px}}
.compm .opts{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.compm button{{background:#333;color:#aaa;border:1px solid #555;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px}}
.compm button:hover{{background:#555;color:#eee}}
.compm button.act{{background:#2d6a4f;color:#b7e4c7;border-color:#40916c}}
.notes{{margin-top:8px;font-size:11px;color:#888}}
.notes label{{display:block;margin-bottom:4px;color:#aaa}}
.notes textarea{{width:100%;background:#0a0a1a;color:#ccc;border:1px solid #333;border-radius:4px;padding:6px;font-size:11px;min-height:50px;resize:vertical}}
.notes textarea:focus{{border-color:#e0c3fc;outline:none}}
.expp{{max-width:900px;margin:15px auto;background:#16213e;border-radius:10px;padding:15px;border:1px solid #333;display:none}}
.expp h3{{color:#b7e4c7;margin-bottom:8px;font-size:14px}}
.expp pre{{background:#0a0a1a;padding:10px;border-radius:8px;color:#ccc;font-size:11px;white-space:pre-wrap;max-height:500px;overflow-y:auto}}
.sum{{max-width:900px;margin:12px auto;padding:10px 15px;background:#0f3460;border-radius:8px;border:1px solid #333;font-size:12px;color:#aaa}}
.sum span{{color:#b7e4c7;font-weight:600}}
</style></head><body>
<h1>{title}</h1>
<p class="sub">Event: {event_id}</p>
<div class="inst"><strong>How to use:</strong> Listen to each TTS line. Edit text if needed for pronunciation/delivery.
Click status badge to cycle: Pending → Approved → Needs Regen. Export when done.
<br><span style="color:#2d6a4f">■</span> Green = audio ready &nbsp;
<span style="color:#776622">■</span> Yellow = pending &nbsp;
<span style="color:#6a3030">■</span> Red = needs regen</div>
<div class="bar">
<button class="b app" onclick="approveAll()" id="aab">✓ Approve All</button>
<button class="b" onclick="playAllAudio()" id="pab">▶ Play All</button>
<button class="b" onclick="stopAll()">⏹ Stop</button>
<button class="b exp" onclick="exportReview()">⬇ Export Review</button>
</div>''')

    parts.append('<div class="tl" id="tl"></div>')
    parts.append('<div class="expp" id="expp"><h3>TTS Review Export — Copy and paste to Claude</h3>')
    parts.append('<pre id="et"></pre><button class="b" onclick="copyExp()" style="margin-top:8px">Copy to Clipboard</button></div>')
    parts.append('<div class="sum" id="sum" style="display:none"></div>')

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

    # Lines data with status tracking
    lines_js = []
    for i, line in enumerate(config.get("lines", [])):
        line_id = line.get("id", f"line_{i:03d}")
        speaker = line.get("speaker", "").replace('"', '\\"')
        text = line.get("text", "").replace('"', '\\"').replace("'", "\\'")
        audio_key = f"audio_{line_id}" if line.get("audio_path") else None
        image_key = line.get("image_key", "none")
        takes = line.get("takes", {})
        takes_keys = {name: f"audio_{line_id}_{name}" for name in takes.keys()}

        audio_key_str = f'"{audio_key}"' if audio_key else "null"
        takes_str = json.dumps(takes_keys)
        lines_js.append(f'{{id:"{line_id}",s:"{speaker}",t:"{text}",a:{audio_key_str},i:"{image_key}",st:"pending",nt:"",tk:{takes_str}}}')

    parts.append("var L=[" + ",\n".join(lines_js) + "];")

    # Core JS engine
    parts.append('''
var cA=null,paA=false,paI=-1;

function render(){
var c=document.getElementById("tl");c.innerHTML="";
for(var i=0;i<L.length;i++){var l=L[i];
var r=document.createElement("div");r.className="cd "+l.st;r.id="r"+i;
// Header
var hd=document.createElement("div");hd.className="hd";
var nm=document.createElement("div");nm.className="ln";nm.textContent=""+(i+1);hd.appendChild(nm);
var sp=document.createElement("span");sp.className="sp";sp.textContent=l.s;hd.appendChild(sp);
var sbb=document.createElement("div");sbb.className="sbb";
var stat=document.createElement("button");stat.className="stat "+l.st;stat.textContent=(l.st==="pending"?"Pending":l.st==="approved"?"✓ Approved":"⚠ Needs Regen");
stat.setAttribute("data-i",""+i);stat.onclick=function(){cycleStatus(parseInt(this.getAttribute("data-i")));};sbb.appendChild(stat);
if(Object.keys(l.tk).length>0){var comp=document.createElement("button");comp.className="comp";comp.innerHTML="Compare Takes ("+Object.keys(l.tk).length+")";
comp.setAttribute("data-i",""+i);comp.onclick=function(){toggleCompare(parseInt(this.getAttribute("data-i")));};sbb.appendChild(comp);}
hd.appendChild(sbb);r.appendChild(hd);
// Body
var bd=document.createElement("div");bd.className="body";
var ta=document.createElement("textarea");ta.className="txt";ta.value=l.t;ta.setAttribute("data-i",""+i);ta.oninput=function(){L[parseInt(this.getAttribute("data-i"))].t=this.value;};bd.appendChild(ta);
// Controls
var ct=document.createElement("div");ct.className="ctrls";
var pb=document.createElement("button");pb.id="pb"+i;
var ha=l.a&&AU[l.a];if(ha){pb.className="pb green";pb.innerHTML="▶";pb.title="Play TTS audio";pb.setAttribute("data-i",""+i);
pb.onclick=function(){playLine(parseInt(this.getAttribute("data-i")));};
}else{pb.className="pb gray";pb.innerHTML="⊗";pb.title="No audio";}
ct.appendChild(pb);
// Image thumbnail
if(l.i!=="none"&&TH[l.i]){var im=document.createElement("img");im.className="th";im.src=TH[l.i];ct.appendChild(im);}
// Takes compare menu (hidden by default)
if(Object.keys(l.tk).length>0){
var compm=document.createElement("div");compm.className="compm";compm.id="compm"+i;compm.style.display="none";
var ts=["primary"];for(var tn in l.tk)ts.push(tn);
var opts=document.createElement("div");opts.className="opts";
for(var j=0;j<ts.length;j++){var tn=ts[j];var btn=document.createElement("button");btn.textContent=tn;btn.className=(j===0?"act":"");
btn.setAttribute("data-i",""+i);btn.setAttribute("data-take",tn);
btn.onclick=function(){var li=parseInt(this.getAttribute("data-i"));var tk=this.getAttribute("data-take");playTake(li,tk);
for(var b of document.querySelectorAll("[data-i='"+li+"'][data-take]")){b.className="";}this.className="act";};opts.appendChild(btn);}
compm.appendChild(opts);ct.appendChild(compm);}
bd.appendChild(ct);
// Notes (for regen-marked lines)
if(l.st==="regen"){var notes=document.createElement("div");notes.className="notes";var nl=document.createElement("label");nl.textContent="Notes for regeneration:";notes.appendChild(nl);
var nta=document.createElement("textarea");nta.value=l.nt;nta.setAttribute("data-i",""+i);nta.oninput=function(){L[parseInt(this.getAttribute("data-i"))].nt=this.value;};notes.appendChild(nta);bd.appendChild(notes);}
r.appendChild(bd);c.appendChild(r);}}

function cycleStatus(i){var sts=["pending","approved","regen"];var ci=sts.indexOf(L[i].st);L[i].st=sts[(ci+1)%sts.length];render();}

function toggleCompare(i){var m=document.getElementById("compm"+i);if(m)m.style.display=(m.style.display==="none"?"flex":"none");}

function playLine(i){
stopAll();var k=L[i].a;if(!k||!AU[k])return;
cA=new Audio(AU[k]);
var b=document.getElementById("pb"+i);var r=document.getElementById("r"+i);
b.className="pb playing";b.innerHTML="⏸";r.classList.add("act");
cA.play().catch(function(e){console.error(e);});
cA.onended=function(){b.className="pb green";b.innerHTML="▶";r.classList.remove("act");cA=null;
if(paA&&paI===i){setTimeout(function(){if(!paA)return;var n=i+1;while(n<L.length&&(!L[n].a||!AU[L[n].a]))n++;
if(n<L.length){paI=n;playLine(n);}else{paA=false;document.getElementById("pab").innerHTML="▶ Play All";}},0.5*1000);}};}

function playTake(i,tk){
stopAll();var k;if(tk==="primary"){k=L[i].a;}else{k=L[i].tk[tk];}
if(!k||!AU[k])return;
cA=new Audio(AU[k]);var b=document.getElementById("pb"+i);var r=document.getElementById("r"+i);
b.className="pb playing";b.innerHTML="⏸";r.classList.add("act");
cA.play().catch(function(e){console.error(e);});
cA.onended=function(){b.className="pb green";b.innerHTML="▶";r.classList.remove("act");cA=null;};}

function playAllAudio(){if(paA){stopAll();return;}paA=true;
var f=-1;for(var i=0;i<L.length;i++){if(L[i].a&&AU[L[i].a]){f=i;break;}}
if(f===-1){alert("No lines have TTS audio yet.");paA=false;return;}
paI=f;document.getElementById("pab").innerHTML="⏹ Stop";playLine(f);}

function stopAll(){paA=false;paI=-1;if(cA){cA.pause();cA=null;}
var bs=document.querySelectorAll(".pb.playing");for(var i=0;i<bs.length;i++){bs[i].className="pb green";bs[i].innerHTML="▶";}
var rs=document.querySelectorAll(".cd.act");for(var i=0;i<rs.length;i++)rs[i].classList.remove("act");}

function approveAll(){for(var i=0;i<L.length;i++){if(L[i].a&&AU[L[i].a]){L[i].st="approved";}}render();}

function exportReview(){
var ep=document.getElementById("expp");ep.style.display="block";
var appd=[],regen=[];
for(var i=0;i<L.length;i++){var l=L[i];
if(l.st==="approved"){appd.push({id:l.id,speaker:l.s,text:l.t,audio_key:l.a});}
else if(l.st==="regen"){regen.push({id:l.id,speaker:l.s,text_original:L[i].t,text_updated:L[i].t,notes:l.nt});}}
var exp={event_id:"''' + event_id + '''",generated_at:new Date().toISOString(),approved_count:appd.length,regen_count:regen.length,approved:appd,needs_regen:regen};
var et=document.getElementById("et");et.textContent=JSON.stringify(exp,null,2);
var sum=document.getElementById("sum");sum.style.display="block";
var ac=0,rc=0;for(var i=0;i<L.length;i++){if(L[i].st==="approved")ac++;else if(L[i].st==="regen")rc++;}
sum.innerHTML="<span>"+ac+" approved</span> &nbsp; | &nbsp; <span>"+rc+" need regen</span> &nbsp; | &nbsp; <span>"+(L.length)+" total</span>";}

function copyExp(){var t=document.getElementById("et").textContent;navigator.clipboard.writeText(t).then(function(){alert("Review manifest copied to clipboard!");});}

render();
''')
    parts.append('</script></body></html>')

    html = '\n'.join(parts)
    with open(output_path, 'w') as f:
        f.write(html)
    print(f"\nTTS Review tool written: {output_path} ({len(html)//1024}KB)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build MindfulNest TTS review HTML")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    build_tts_review(config, args.output)


if __name__ == "__main__":
    main()
