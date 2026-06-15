#!/bin/bash
cd /Users/kimberlysmith/Projects/mindfulnest-tooling/Production/tools
python3 -m py_compile server_handlers/background.py && echo "✓ background.py OK"
python3 -m py_compile server_handlers/phases.py && echo "✓ phases.py OK"
python3 -m py_compile production_server.py && echo "✓ production_server.py OK"
python3 -m py_compile magic_compositor.py && echo "✓ magic_compositor.py OK"
python3 -m py_compile build_storyboard.py && echo "✓ build_storyboard.py OK"
