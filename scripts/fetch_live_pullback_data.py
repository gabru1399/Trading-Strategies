import urllib.request
import json

symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
out = {}
for s in symbols:
    # 1. Market Overview
    try:
        req = urllib.request.urlopen(f'http://localhost:3000/api/cg/market?sym={s}', timeout=5)
        m = json.loads(req.read().decode())
    except Exception as e:
        m = {'error': str(e)}
        
    # 2. Book Walls
    try:
        req_w = urllib.request.urlopen(f'http://localhost:3000/api/cg/bookwalls?sym={s}&limit=20', timeout=5)
        w = json.loads(req_w.read().decode())
    except Exception as e:
        w = {'error': str(e)}
        
    # 3. Liquidation Levels
    try:
        req_l = urllib.request.urlopen(f'http://localhost:3000/api/cg/liqlevels?sym={s}', timeout=5)
        l = json.loads(req_l.read().decode())
    except Exception as e:
        l = {'error': str(e)}

    out[s] = {'market': m, 'walls': w, 'liq': l}

summary = {}
for s in symbols:
    m = out[s].get('market', {})
    w = out[s].get('walls', {})
    l = out[s].get('liq', {})
    
    price = m.get('price', {}).get('last') if isinstance(m.get('price'), dict) else m.get('price')
    vwap_day = m.get('vwap', {}).get('day')
    auction_day = m.get('auction', {}).get('day', {})
    auction_sess = m.get('auction', {}).get('session', {})
    ema15m = m.get('ema', {}).get('m15', {})
    ema1h = m.get('ema', {}).get('h1', {})
    
    # Book walls
    walls_list = w.get('walls', []) if isinstance(w, dict) else []
    asks = [b for b in walls_list if b.get('side') == 'ask']
    bids = [b for b in walls_list if b.get('side') == 'bid']
    
    # Liq levels model
    model = l.get('model', {}) if isinstance(l, dict) else {}
    short_levels = model.get('shortLevels', []) or l.get('shortLevels', [])
    overhead_short_liq = [x for x in short_levels if x.get('price', 0) > (price or 0)][:5]
    
    summary[s] = {
        'last_price': price,
        'day_vwap': vwap_day,
        'day_val': auction_day.get('val'),
        'day_poc': auction_day.get('poc'),
        'day_vah': auction_day.get('vah'),
        'sess_val': auction_sess.get('val'),
        'sess_poc': auction_sess.get('poc'),
        'sess_vah': auction_sess.get('vah'),
        'ema15m': ema15m,
        'ema1h': ema1h,
        'top_ask_walls': asks[:4],
        'top_bid_walls': bids[:3],
        'overhead_short_liq': overhead_short_liq
    }

print(json.dumps(summary, indent=2))
with open('c:/Users/SIGMA/Documents/Trading-Strategies/scratch_pullback_summary.json', 'w') as f:
    json.dump(summary, f, indent=2)
