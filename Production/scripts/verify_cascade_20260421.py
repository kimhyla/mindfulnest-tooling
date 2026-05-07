import urllib.request, urllib.parse, json, sys

BASE = "https://directus-production-3460.up.railway.app"

def login():
    data = json.dumps({"email":"kimhyla11@gmail.com","password":"directus11$"}).encode()
    req = urllib.request.Request(BASE+"/auth/login", data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["data"]["access_token"]

def get(path, token):
    req = urllib.request.Request(BASE+path, headers={"Authorization":f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

token = login()
print("=== TOKEN OK ===")

print("\n--- CHECK 1: prod_locked_decisions ---")
for ld_id in [332, 335, 352, 353, 354, 355, 356]:
    try:
        d = get(f"/items/prod_locked_decisions/{ld_id}", token)["data"]
        name = d.get('decision_name') or ''
        print(f"LD-{ld_id}: key={d.get('decision_key')} | name={name[:60]} | date={d.get('date_locked')} | status={d.get('status')}")
    except Exception as e:
        print(f"LD-{ld_id}: MISSING/ERROR - {e}")

print("\n--- CHECK 2: prod_session_decisions 38,39 ---")
for sd_id in [38, 39]:
    try:
        d = get(f"/items/prod_session_decisions/{sd_id}", token)["data"]
        print(f"SD-{sd_id}: decided_by={d.get('decided_by')} | decision={str(d.get('decision'))[:100]}")
    except Exception as e:
        print(f"SD-{sd_id}: ERROR - {e}")

print("\n--- CHECK 3: prod_preflight_reviews 137-141 ---")
for pf_id in [137, 138, 139, 140, 141]:
    try:
        d = get(f"/items/prod_preflight_reviews/{pf_id}", token)["data"]
        print(f"PF-{pf_id}: approved={d.get('approved_to_proceed')} | task_id={d.get('task_id')} | classification={d.get('classification')}")
    except Exception as e:
        print(f"PF-{pf_id}: MISSING - {e}")

print("\n--- CHECK 4: prod_reference_docs ---")
for key in ["SCOPE_REVERSAL_ARC8", "SCOPE_REVERSAL_BENSON", "STILLGEN_PHASE0"]:
    try:
        q = urllib.parse.quote(key)
        d = get(f"/items/prod_reference_docs?filter[file_path][_contains]={q}&fields=id,file_path,status", token)["data"]
        if d:
            for row in d:
                print(f"  {key}: id={row.get('id')} | path={row.get('file_path')} | status={row.get('status')}")
        else:
            print(f"  {key}: NO MATCHES")
    except Exception as e:
        print(f"  {key}: ERROR - {e}")

print("\n--- CHECK 5: prod_activity_log recent 50 ---")
try:
    d = get("/items/prod_activity_log?sort=-id&limit=50&fields=id,task_id,status,action", token)["data"]
    target_tasks = ["scope-reversal-arc8-back-20260420", "scope-reversal-benson-back-20260421", "stillgen-addon-phase0-20260421"]
    counts = {t:0 for t in target_tasks}
    errors = []
    for row in d:
        tid = row.get("task_id") or ""
        for t in target_tasks:
            if t in tid:
                counts[t] += 1
        if (row.get("status") or "").upper() in ("ERROR","FAILED"):
            errors.append(f"id={row['id']} task={tid} status={row.get('status')}")
    for t,c in counts.items():
        print(f"  {t}: {c} entries")
    print(f"  ERRORS: {len(errors)}")
    for e in errors:
        print(f"    {e}")
except Exception as e:
    print(f"  ERROR: {e}")
