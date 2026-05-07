#!/usr/bin/env python3
"""
sync_reference_docs.py — Registry Sync Check for prod_reference_docs

Compares all active Directus registry entries against actual files on disk.
Flags: MISSING (registered but not on disk), NEW (on disk but not registered),
PATH MISMATCH (file renamed but registry shows old name).

Usage:
    python3 sync_reference_docs.py                  # Full sync check (default)
    python3 sync_reference_docs.py --session-start   # Same as default, formatted for session start
    python3 sync_reference_docs.py --session-end     # Same check, formatted as safety-net audit
    python3 sync_reference_docs.py --quick           # Just counts, no details

Requires: API_KEYS_MASTER.md for Directus credentials.
Uses Python urllib (never curl — password contains $, lesson T-2).

Part of CLAUDE.md Rule 15: Reference Docs Registry Sync Protocol.
"""

import urllib.request
import json
import os
import sys
import glob


def get_directus_token(base_url, email, password):
    """Authenticate and return JWT token."""
    auth_data = json.dumps({'email': email, 'password': password}).encode()
    req = urllib.request.Request(
        f'{base_url}/auth/login',
        data=auth_data,
        headers={'Content-Type': 'application/json'}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp['data']['access_token']


def get_registry_entries(base_url, token):
    """Query all active entries from prod_reference_docs."""
    req = urllib.request.Request(
        f'{base_url}/items/prod_reference_docs?fields=id,doc_title,file_path,status,is_current,doc_version,updated_at&filter[status][_neq]=archived&limit=200&sort=id',
        headers={'Authorization': f'Bearer {token}'}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp['data']


def scan_disk_files(project_root):
    """Scan project folder for .md, .docx, .xlsx files in root and key subdirectories."""
    disk_files = {}  # basename -> full_path

    # Scan root
    for ext in ['*.md', '*.docx', '*.xlsx', '*.html']:
        for f in glob.glob(os.path.join(project_root, ext)):
            basename = os.path.basename(f)
            disk_files[basename] = f

    # Scan key subdirectories (where registered docs live)
    subdirs = ['Production', 'Business', 'Clinical', 'App Design', 'Parent Coach',
               'Canon', 'video_pipeline', 'Old Versions', 'Arc Skeletons']
    for subdir in subdirs:
        subdir_path = os.path.join(project_root, subdir)
        if os.path.isdir(subdir_path):
            for ext in ['*.md', '*.docx', '*.xlsx']:
                for f in glob.glob(os.path.join(subdir_path, ext)):
                    # Store with subdir prefix to match registry file_path format
                    rel_path = os.path.relpath(f, project_root)
                    basename = os.path.basename(f)
                    disk_files[rel_path] = f
                    disk_files[basename] = f  # Also index by basename for fuzzy matching

    return disk_files


def run_sync_check(project_root, base_url, email, password, mode='full'):
    """Main sync check. Returns (issues_found, report_lines)."""

    report = []
    issues = []

    # Step 1: Authenticate
    try:
        token = get_directus_token(base_url, email, password)
    except Exception as e:
        return True, [f"ERROR: Directus auth failed: {e}"]

    # Step 2: Get registry entries
    registry = get_registry_entries(base_url, token)
    report.append(f"Registry: {len(registry)} entries (excluding archived)")

    # Step 3: Scan disk
    disk_files = scan_disk_files(project_root)
    unique_files = set()
    for k, v in disk_files.items():
        unique_files.add(v)
    report.append(f"Disk: {len(unique_files)} files found in project folder + subdirectories")

    # Step 4: Check each registry entry against disk
    missing = []
    found = []

    for entry in registry:
        file_path = entry.get('file_path', '')
        if not file_path:
            missing.append((entry, 'NO FILE_PATH SET'))
            continue

        # Try exact match first (with subdir path)
        basename = os.path.basename(file_path)

        if file_path in disk_files:
            found.append(entry)
        elif basename in disk_files:
            # File exists but at different path than registered
            actual_path = os.path.relpath(disk_files[basename], project_root)
            if actual_path != file_path:
                issues.append({
                    'type': 'PATH_MISMATCH',
                    'id': entry['id'],
                    'title': entry['doc_title'],
                    'registry_path': file_path,
                    'disk_path': actual_path
                })
            found.append(entry)
        else:
            missing.append((entry, 'FILE NOT FOUND ON DISK'))
            issues.append({
                'type': 'MISSING',
                'id': entry['id'],
                'title': entry['doc_title'],
                'registry_path': file_path
            })

    # Step 5: Check for unregistered files (only in root — subdirs may have non-registry files)
    registered_basenames = set()
    for entry in registry:
        fp = entry.get('file_path', '')
        if fp:
            registered_basenames.add(os.path.basename(fp))

    # Only flag root-level .md/.docx that look like reference docs
    # Skip: meta files, working artifacts, handoffs, reports, proposals, backups, READMEs
    skip_patterns = {'CLAUDE.md', 'README.md', '.DS_Store'}
    # Skip prefixes that indicate working artifacts (not reference docs)
    skip_prefixes = (
        'HANDOFF_',           # Session handoff prompts (temporary)
        'SESSION_',           # Session-specific notes
        'REPAIR_',            # One-time repair logs
        'STALENESS_',         # One-time audit reports
        'PIPELINE_AUDIT_',    # One-time audit reports
        'CLAUDE_backup_',     # Backup files
        'CLAUDE_MD_',         # CLAUDE.md proposals/slimming docs
        'INTERACTION_',       # Working artifacts from agent runs
        'README_',            # README files
        'Chapter_',           # Dissertation chapters (separate workflow)
        'Mindfulness_Project_Kim_Smith',  # Dissertation file
        'AIUS',               # Academic review (separate workflow)
        'MindfulNest_Account_', # Billing summaries (one-off)
        'BLENDER_3D_',        # One-off cost analyses (superseded by visual style decision)
        'FOLDER_REORGANIZATION', # One-off proposal
        'HYBRID_LIPSYNC_',    # Superseded proposal (lip sync decision made)
        'LIP_SYNC_DECISION',  # Superseded (decision captured in CLAUDE.md Rule 8)
        'MVP_TIMELINE_',      # One-off comparison
        'NANO_BANANA_',       # Superseded pipeline (Gemini approach abandoned)
        'STYLE_TRANSFER_',    # One-off research (visual style locked)
        'EVENT_1_',           # Event-specific working docs
        'ARC_1_DIALOGUE_',    # Working extraction (not reference)
        'ARC_1_PRODUCTION_PIPELINE_REPORT', # One-off reports
        'ANIMATION_REVIEW_BUILDER_AUDIT', # One-off audit
        'AI_GAME_ART_',       # Research/examples (not reference)
        'SCREENWRITING_',     # Research docs (not production reference)
        'RESEARCH_CLAUDE_',   # Research docs
        'PRODUCTION_PLAN_EFFICIENCY', # One-off analysis
        'PIPELINE_SPEED_OPTIMIZATION_ANALYSIS', # Superseded by SPEED decisions in Directus
        'PIPELINE_OPTIMIZATION_TECHNICAL', # One-off technical note
        'PIPELINE_ORCHESTRATOR_IMPLEMENTATION', # Superseded by pipeline.py
        'PIPELINE_BRAIN_ORCHESTRATOR_ADDENDUM', # Addendum merged into Pipeline Brain
        'MINDFULNEST_PRODUCTION_SYSTEM_PRD', # One-off assessment
        'VISUAL_GENERATION_FAILURE', # One-off failure analysis
        'VISUAL_PIPELINE_FAILURE', # One-off failure analysis
        'VISUAL_PIPELINE_RESEARCH', # One-off research report
        'VISUAL_PIPELINE_DOCUMENTATION_SUMMARY', # One-off summary
        'VISUAL_PIPELINE_TEST_STRATEGY', # Superseded by visual style decision
        'VIDEO_PIPELINE_TESTING_', # One-off testing doc
        'MINDFULNEST_VISUAL_ARCHITECTURE', # One-off analysis (visual style locked)
        'MINDFULNEST_VISUAL_PIPELINE_TEST', # Superseded by visual style decision
        'MindfulNest_PRD_',    # PRD docs (app architecture doc supersedes these)
        'SUPABASE_OPERATIONS', # Ops guide (infrastructure, not reference)
        'VISUAL_AND_ANIMATION_PIPELINE_LOCKED', # Decisions captured in CLAUDE.md Rule 8 + memory
        'VISUAL_FEEDBACK_TEST_', # Working test results (not reference)
        'CLAUDE_CODE_HANDOFF_', # Claude Code-specific handoffs (not reference docs)
    )
    # Skip suffixes that indicate working artifacts
    skip_suffixes = (
        '_COMPLETE.md',       # Completion logs
        '_INDEX.md',          # Index files (not reference docs)
    )
    root_files = set()
    for ext in ['*.md', '*.docx']:
        for f in glob.glob(os.path.join(project_root, ext)):
            bn = os.path.basename(f)
            if bn in skip_patterns or bn.startswith('.'):
                continue
            if any(bn.startswith(p) for p in skip_prefixes):
                continue
            if any(bn.endswith(s) for s in skip_suffixes):
                continue
            root_files.add(bn)

    new_files = root_files - registered_basenames
    for nf in sorted(new_files):
        issues.append({
            'type': 'NEW',
            'filename': nf,
            'location': 'project root'
        })

    # Step 6: Build report
    report.append(f"Matched: {len(found)}/{len(registry)} registry entries found on disk")

    if not issues:
        report.append("")
        report.append("✅ SYNC CHECK PASSED — registry matches disk perfectly.")
    else:
        report.append("")
        report.append(f"⚠️  {len(issues)} ISSUE(S) FOUND:")
        report.append("")

        for issue in issues:
            if issue['type'] == 'MISSING':
                report.append(f"  MISSING  #{issue['id']} \"{issue['title']}\"")
                report.append(f"           Registry path: {issue['registry_path']}")
                report.append(f"           → File not found on disk. Delete entry or has it moved?")
                report.append("")
            elif issue['type'] == 'PATH_MISMATCH':
                report.append(f"  MISMATCH #{issue['id']} \"{issue['title']}\"")
                report.append(f"           Registry: {issue['registry_path']}")
                report.append(f"           Disk:     {issue['disk_path']}")
                report.append(f"           → Update registry path?")
                report.append("")
            elif issue['type'] == 'NEW':
                report.append(f"  NEW      \"{issue['filename']}\"")
                report.append(f"           Location: {issue['location']}")
                report.append(f"           → Register in prod_reference_docs?")
                report.append("")

    return len(issues) > 0, report


def find_project_root():
    """Find the MindfulNest project folder. Checks env var, session mounts, and Mac Dropbox."""
    # 1. Explicit env var (highest priority)
    env_root = os.environ.get('PROJECT_ROOT')
    if env_root and os.path.isdir(env_root):
        return env_root

    # 2. Dynamic session mount detection (works across ALL Cowork sessions)
    #    Scans /sessions/*/mnt/ for the project folder, including Dropbox subfolder
    for pattern in [
        '/sessions/*/mnt/Dropbox/Claude Mindfulnest Project Files',
        '/sessions/*/mnt/Claude Mindfulnest Project Files',
    ]:
        session_matches = glob.glob(pattern)
        if session_matches:
            # Use the most recently modified match
            session_matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return session_matches[0]

    # 3. Mac Dropbox path (when running directly on Kim's Mac via Claude Code)
    mac_path = os.path.expanduser('~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files')
    if os.path.isdir(mac_path):
        return mac_path

    return None


def main():
    # Configuration
    project_root = find_project_root()

    if not project_root:
        print("ERROR: Could not find project folder.")
        print("Options:")
        print("  1. Set PROJECT_ROOT env var: export PROJECT_ROOT=/path/to/Claude Mindfulnest Project Files")
        print("  2. Run from a Cowork session with the project folder mounted")
        print("  3. Run on Kim's Mac with Dropbox synced")
        sys.exit(1)

    print(f"Project root: {project_root}")

    # Directus credentials
    base_url = 'https://directus-production-3460.up.railway.app'
    email = 'kimhyla11@gmail.com'
    password = 'directus11$'

    # Parse mode
    mode = 'full'
    if '--session-start' in sys.argv:
        mode = 'session-start'
    elif '--session-end' in sys.argv:
        mode = 'session-end'
    elif '--quick' in sys.argv:
        mode = 'quick'

    # Header
    if mode == 'session-start':
        print("=" * 60)
        print("REFERENCE DOCS SYNC CHECK — SESSION START")
        print("=" * 60)
    elif mode == 'session-end':
        print("=" * 60)
        print("REFERENCE DOCS SYNC CHECK — SESSION END (safety net)")
        print("=" * 60)
    else:
        print("=" * 60)
        print("REFERENCE DOCS SYNC CHECK")
        print("=" * 60)

    has_issues, report = run_sync_check(project_root, base_url, email, password, mode)

    for line in report:
        print(line)

    if has_issues:
        print("")
        print("ACTION REQUIRED: Resolve issues above before proceeding.")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
