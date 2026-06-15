import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from streamlit_image_coordinates import streamlit_image_coordinates
import io
from PIL import Image
import json
import os
import copy

# ==========================================
# 1. 設定 & CSS
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.9.11", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 4rem; padding-bottom: 6rem; }
    
    div[data-testid="stHorizontalBlock"] { gap: 4px !important; }
    div.stButton { margin-bottom: 4px !important; }
    
    div.stButton > button {
        width: 100%; 
        height: 75px; 
        font-weight: 900; 
        font-size: 24px; 
        border-radius: 8px; 
        margin: 0 !important; 
        padding: 0 !important;
        touch-action: manipulation;
    }
    
    .keypad-btn > button { height: 80px !important; font-size: 32px !important; }
    
    div.stDownloadButton > button {
        background-color: #FF4B4B; color: white; height: 80px; font-size: 24px;
        border: 2px solid white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .score-board { font-size: 40px; font-weight: 900; text-align: center; background: #333; color: white; padding: 5px; border-radius: 8px; }
    .input-card { background-color: #f8f9fa; padding: 10px; border-radius: 15px; border: 2px solid #e9ecef; }
    .step-header { font-size: 20px; font-weight: bold; color: #4c78a8; margin-bottom: 5px; border-bottom: 2px solid #4c78a8; }
    .rot-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; text-align: center; font-weight: bold; font-size: 14px; }
    .rot-cell { border: 1px solid #555; padding: 8px; background: white; border-radius: 6px; }
    .rot-front { background: #ffebeb; }
    .rot-server { border: 3px solid red; color: red; font-weight: 900; }
</style>
""", unsafe_allow_html=True)

defaults = {
    'stage': 0, 'roster_cursor': 0, 'temp_roster': [], 'scout_step': 0,
    'set_name': '1', 'video_url': '', 'liberos': [], 'rotation': [], 'score': [0, 0], 'phase': 'R',
    'current_input_data': {}, 'data_log': [], 'points': [], 
    'setter_counts': {}, 'player_counts': {}, 'all_players': [],
    'key_map': 0, 'time_buffer': "", 'key_roster': 0, 'history_stack': [], 'custom_combo_pool': {},
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

FIXED_COMBOS_TOP = ['V5', 'X5', 'VC', 'XC']
FIXED_COMBOS_MID = ['Q1', 'Q3', 'B1', 'BC']
ALL_FIXED_COMBOS = FIXED_COMBOS_TOP + FIXED_COMBOS_MID

SAVE_DATA_FILE = "autosave_data.csv"
SAVE_STATE_FILE = "autosave_state.json"

# ==========================================
# 2. ロジック関数
# ==========================================
def save_state_to_history():
    state_snapshot = {
        'score': copy.deepcopy(st.session_state.score),
        'rotation': copy.deepcopy(st.session_state.rotation),
        'phase': st.session_state.phase,
        'setter_counts': copy.deepcopy(st.session_state.setter_counts),
        'player_counts': copy.deepcopy(st.session_state.player_counts),
        'custom_combo_pool': copy.deepcopy(st.session_state.custom_combo_pool)
    }
    st.session_state.history_stack.append(state_snapshot)
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

def undo_last_action():
    if not st.session_state.data_log:
        st.warning("No data to delete")
        return
    st.session_state.data_log.pop()
    if st.session_state.history_stack:
        prev = st.session_state.history_stack.pop()
        st.session_state.score = prev['score']
        st.session_state.rotation = prev['rotation']
        st.session_state.phase = prev['phase']
        st.session_state.setter_counts = prev['setter_counts']
        st.session_state.player_counts = prev['player_counts']
        st.session_state.custom_combo_pool = prev['custom_combo_pool']
        st.toast("Undo Successful", icon="↩️")
    auto_save()
    st.rerun()

def auto_save():
    if len(st.session_state.data_log) > 0:
        pd.DataFrame(st.session_state.data_log).to_csv(SAVE_DATA_FILE, index=False)
    state_data = {
        "score": st.session_state.score, "rotation": st.session_state.rotation, "phase": st.session_state.phase,
        "set_name": st.session_state.set_name, "video_url": st.session_state.video_url, "liberos": st.session_state.liberos,
        "setter_counts": st.session_state.setter_counts, "player_counts": st.session_state.player_counts,
        "all_players": st.session_state.all_players,
        "custom_combo_pool": st.session_state.custom_combo_pool, "stage": st.session_state.stage
    }
    with open(SAVE_STATE_FILE, 'w') as f: json.dump(state_data, f)

def coords_to_zone(lx, ly):
    if lx < 0 or lx > 9 or ly < 0 or ly > 18: return "Out"
    r = int(min(max(ly, 0), 17.99) // 3)
    c = int(min(max(lx, 0), 8.99) // 3)
    if r < 3: return str([[5,6,1], [7,8,9], [4,3,2]][r][c])
    else: return str([[2,3,4], [1,6,5]][0 if ly < 13.5 else 1][c])

def create_court_img(points):
    fig, ax = plt.subplots(figsize=(3.75, 6))
    ax.add_patch(patches.Rectangle((-3, -3), 15, 24, fc='#e0e0e0', ec='none'))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    
    ax.plot([3,3], [0,18], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=1)
    ax.plot([6,6], [0,18], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=1)
    ax.plot([0,9], [3,3], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=1)
    ax.plot([0,9], [15,15], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=1)
    
    ax.plot([0,9], [9,9], c='red', lw=3, zorder=2)
    ax.plot([0,9], [6,6], c='black', lw=2, zorder=2)
    ax.plot([0,9], [12,12], c='black', lw=2, zorder=2)
    ax.plot([-3,-3,12,12,-3], [-3,21,21,-3,-3], c='black', lw=2)

    for i, p in enumerate(points):
        lx, ly = p[2], p[3]
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(lx, ly, s=150, c=col, zorder=10, edgecolors='white')
        ax.text(lx, ly, lbl, color='white', ha='center', va='center', fontweight='bold', fontsize=8)
        if i==1: 
            sx, sy = points[0][2], points[0][3]
            ax.arrow(sx, sy, (lx-sx)*0.85, (ly-sy)*0.85, width=0.15, color='gray', alpha=0.5, length_includes_head=True)
            
    ax.set_xlim(-3, 12); ax.set_ylim(-3, 21); ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return Image.open(buf)

def format_time(val):
    s = str(val).strip()
    if len(s) == 0: return "00:00"
    v = int(s)
    if len(s) <= 2: return f"00:{v:02d}"
    sec = int(s[-2:]); min_ = int(s[:-2])
    return f"{min_:02d}:{sec:02d}"

def time_to_sec(t_str):
    if ':' not in t_str: return 0
    m, s = t_str.split(':')
    return int(m)*60 + int(s)

def rotate_team():
    r = st.session_state.rotation
    st.session_state.rotation = [r[-1]] + r[:-1]
    auto_save()

def update_score(winner):
    if winner == 'my':
        st.session_state.score[0] += 1
        if st.session_state.phase == 'R':
            rotate_team()
            st.toast("Sideout!", icon="⭕")
        else:
            st.toast("Break!", icon="⭕")
        st.session_state.phase = 'S'
    elif winner == 'op':
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast("Op Point", icon="❌")
    auto_save()

def count_setter_usage(name):
    if name and name != "Direct/Two":
        st.session_state.setter_counts[name] = st.session_state.setter_counts.get(name, 0) + 1

def count_custom_combo(combo):
    if combo and combo not in ALL_FIXED_COMBOS:
        st.session_state.custom_combo_pool[combo] = st.session_state.custom_combo_pool.get(combo, 0) + 1

def commit_record(quality, winner=None):
    save_state_to_history()
    curr = st.session_state.current_input_data
    
    if curr.get('skill') == 'A':
        count_custom_combo(curr.get('combo', ''))

    s_z, e_z = "", ""
    s_x, s_y, e_x, e_y = "", "", "", ""
    if len(st.session_state.points) >= 1: 
        s_x, s_y = st.session_state.points[0][2], st.session_state.points[0][3]
        s_z = coords_to_zone(s_x, s_y)
    if len(st.session_state.points) >= 2: 
        e_x, e_y = st.session_state.points[1][2], st.session_state.points[1][3]
        e_z = coords_to_zone(e_x, e_y)

    # ==============================================================
    # ★ 変更点: Y座標の差分（ベクトルの向き）だけで反転を判定する
    # ==============================================================
    is_bottom_to_top = False
    if s_y != "" and e_y != "":
        # 始点より終点の方が奥（Y座標が大きい）なら下から上への攻撃
        if s_y < e_y: 
            is_bottom_to_top = True
    elif s_y != "" and e_y == "":
        # サーブ等の1点タップで差分が取れない場合のみ、コートの半分より手前かで判定
        if s_y < 9: 
            is_bottom_to_top = True

    if is_bottom_to_top:
        s_x = 9.0 - s_x
        s_y = 18.0 - s_y
        s_z = coords_to_zone(s_x, s_y)
        if e_x != "":
            e_x = 9.0 - e_x
            e_y = 18.0 - e_y
            e_z = coords_to_zone(e_x, e_y)
    # ==============================================================

    final_row = {
        "set": st.session_state.set_name,
        "score": f"{st.session_state.score[0]}-{st.session_state.score[1]}",
        "phase": st.session_state.phase,
        "setter": curr.get('setter',''), "player": curr.get('player',''),
        "skill": curr.get('skill',''), "combo": curr.get('combo',''),
        "quality": quality,
        "start_zone": s_z, "end_zone": e_z,
        "start_x": s_x, "start_y": s_y, "end_x": e_x, "end_y": e_y,
        "memo": "", "video_url": st.session_state.video_url,
        "video_time": time_to_sec(curr.get('time',''))
    }
    st.session_state.data_log.append(final_row)
    
    if winner: update_score(winner)
    else:
        skill = curr.get('skill','')
        if (skill in ['A','B','S'] and quality=='#') or (skill=='A' and quality=='T'): update_score('my')
        elif quality == '^': update_score('op')
        else: st.toast("Saved", icon="✅")

    st.session_state.points = []
    st.session_state.current_input_data = {}
    st.session_state.scout_step = 0
    st.session_state.key_map += 1
    st.session_state.time_buffer = "" 
    auto_save()
    st.rerun()

def get_sorted_players():
    return sorted(st.session_state.all_players, key=lambda n: st.session_state.player_counts.get(n, 0), reverse=True)

def get_sorted_setters():
    return sorted(st.session_state.all_players, key=lambda n: st.session_state.setter_counts.get(n, 0), reverse=True) + ["Direct/Two"]

def get_custom_combos():
    sorted_c = sorted(st.session_state.custom_combo_pool.items(), key=lambda x: x[1], reverse=True)
    return [x[0] for x in sorted_c]

# ==========================================
# 3. アプリ進行フロー
# ==========================================
with st.sidebar:
    st.header("💾 Save Data")
    if os.path.exists(SAVE_STATE_FILE):
        st.info("前回のデータが見つかりました")
        if st.button("📂 続きから再開"):
            try:
                if os.path.exists(SAVE_DATA_FILE):
                    df = pd.read_csv(SAVE_DATA_FILE)
                    st.session_state.data_log = df.to_dict('records')
                with open(SAVE_STATE_FILE, 'r') as f:
                    d = json.load(f)
                    st.session_state.score = d["score"]; st.session_state.rotation = d["rotation"]
                    st.session_state.phase = d["phase"]; st.session_state.set_name = d["set_name"]
                    st.session_state.video_url = d["video_url"]; st.session_state.liberos = d["liberos"]
                    st.session_state.setter_counts = d.get("setter_counts", {}) 
                    st.session_state.player_counts = d.get("player_counts", {})
                    st.session_state.all_players = d.get("all_players", [p for p in d["rotation"] + d["liberos"] if p]) 
                    st.session_state.custom_combo_pool = d.get("custom_combo_pool", {})
                    st.session_state.stage = 6
                st.toast("Resumed!", icon="📂"); st.rerun()
            except Exception as e: st.error(f"Load failed: {e}")
    else: st.caption("保存されたデータはありません")

if st.session_state.stage < 6:
    st.title("🛠️ Game Setup")
    if st.session_state.stage == 0:
        st.subheader("Step 1: Set Number")
        val = st.text_input("Set", value="1")
        if st.button("Next"): st.session_state.set_name = val; st.session_state.stage = 1; auto_save(); st.rerun()
    elif st.session_state.stage == 1:
        st.subheader("Step 2: Video URL")
        val = st.text_input("URL", value="")
        if st.button("Next"): st.session_state.video_url = val; st.session_state.stage = 2; auto_save(); st.rerun()
    elif st.session_state.stage == 2:
        idx = st.session_state.roster_cursor
        pos_names = ["1 (Server)", "6 (Back-C)", "5 (Back-L)", "4 (Front-L)", "3 (Front-C)", "2 (Front-R)"]
        st.subheader(f"Step 3: Lineup ({idx+1}/6)")
        st.info(f"Position: **{pos_names[idx]}**")
        k = f"roster_{idx}_{st.session_state.key_roster}"
        p_name = st.text_input("Player Name", key=k)
        if st.button("Add Player"):
            if p_name:
                st.session_state.temp_roster.append(p_name)
                st.session_state.key_roster += 1
                if st.session_state.roster_cursor < 5: st.session_state.roster_cursor += 1
                else: st.session_state.stage = 3
                st.rerun()
    elif st.session_state.stage == 3:
        st.subheader("Step 4: Confirm")
        r = st.session_state.temp_roster
        st.markdown(f"""<div class="rot-grid"><div class="rot-cell rot-front">4: {r[3]}</div><div class="rot-cell rot-front">3: {r[4]}</div><div class="rot-cell rot-front">2: {r[5]}</div><div class="rot-cell">5: {r[2]}</div><div class="rot-cell">6: {r[1]}</div><div class="rot-cell rot-server">1: {r[0]}</div></div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("OK"): st.session_state.rotation = st.session_state.temp_roster; st.session_state.stage = 4; auto_save(); st.rerun()
        if c2.button("Retry"): st.session_state.stage = 2; st.session_state.roster_cursor = 0; st.session_state.temp_roster = []; st.rerun()
    elif st.session_state.stage == 4:
        st.subheader("Step 5: Liberos")
        val = st.text_input("Names (comma separated)")
        if st.button("Next"): st.session_state.liberos = [x.strip() for x in val.split(',')] if val else []; st.session_state.stage = 5; auto_save(); st.rerun()
    elif st.session_state.stage == 5:
        st.subheader("Step 6: First Phase")
        c1, c2 = st.columns(2)
        if c1.button("Serve (We)"): 
            st.session_state.all_players = [p for p in st.session_state.rotation + st.session_state.liberos if p]
