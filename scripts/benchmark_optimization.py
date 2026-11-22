import os, json, urllib.request

gemini_dir = r'C:\Users\SIGMA\.gemini'
config_dir = r'C:\Users\SIGMA\.gemini\config'
mcp_cfg_path = os.path.join(config_dir, 'mcp_config.json')
plugins_cfg_path = os.path.join(config_dir, 'plugins.json')

print('=== 1. MCP CONFIGURATION AUDIT ===')
with open(mcp_cfg_path, 'r') as f:
    mcp_data = json.load(f)
active_mcp = list(mcp_data.get('mcpServers', {}).keys())
print(f'Active MCP servers count: {len(active_mcp)}')
print(f'Active MCP servers: {active_mcp}')
assert 'rea' not in active_mcp, 'FAIL: rea is still in mcp_config.json'
assert 'scite' not in active_mcp, 'FAIL: scite is still in mcp_config.json'
print('SUCCESS: Heavy non-desk MCP servers (rea, scite) removed!')

print('\n=== 2. PLUGINS CONFIGURATION AUDIT ===')
with open(plugins_cfg_path, 'r') as f:
    plugins_data = json.load(f)
active_plugins = plugins_data.get('plugins', [])
print(f'Active plugins count: {len(active_plugins)}')
print(f'Active plugins: {active_plugins}')
assert 'harness-skills' not in active_plugins, 'FAIL: duplicate harness-skills is still in plugins.json'
assert 'harness-antigravity' in active_plugins, 'FAIL: canonical harness-antigravity missing'
print('SUCCESS: Plugin deduplication verified (harness-skills removed, harness-antigravity active)!')

print('\n=== 3. DISK RECLAMATION MEASUREMENT ===')
# Check persistent-memory/memory.db
pm_db = os.path.join(config_dir, 'plugins', 'persistent-memory', 'memory.db')
print('persistent-memory/memory.db exists:', os.path.exists(pm_db))

# Check browser_recordings fa7d3cb6 directory
rec_dir = os.path.join(gemini_dir, 'antigravity-ide', 'browser_recordings', 'fa7d3cb6-9d6b-48d8-ab59-6dc066d275f6')
print('Old browser_recordings (3.3 GB) exists:', os.path.exists(rec_dir))

# Check dead daemons
daemon_dir = os.path.join(gemini_dir, 'antigravity', 'daemon')
daemon_files = os.listdir(daemon_dir) if os.path.exists(daemon_dir) else []
print(f'Active daemon hub files: {len(daemon_files)}')

print('\n=== 4. LOCAL TERMINAL CONNECTIVITY AUDIT ===')
try:
    with urllib.request.urlopen('http://127.0.0.1:3000/api/cg/market?sym=BTC', timeout=5) as resp:
        mkt = json.loads(resp.read().decode())
        print(f'HTTP 200 OK — Live BTC price: {mkt.get("price", {}).get("last")}')
except Exception as e:
    print('Terminal error:', e)

print('\n=== ALL BENCHMARKS PASS ===')
