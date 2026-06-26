import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from matplotlib import font_manager
import urllib.request
import re
import os
import tempfile
import io

# PDF生成用ライブラリの読み込み
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# ==========================================
# 0. 日本語フォント設定
# ==========================================
def init_japanese_font():
    font_path = "ipaexg.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/minoryorg/ipaexg/raw/master/ipaexg.ttf"
        try:
            urllib.request.urlretrieve(url, font_path)
        except: return 
    if os.path.exists(font_path):
        font_manager.fontManager.addfont(font_path)
        plt.rcParams['font.family'] = 'IPAexGothic'

init_japanese_font()

# ==========================================
# 1. 設定 & 関数定義
# ==========================================
st.set_page_config(page_title="Volleyball Analyst Pro", layout="wide")

st.markdown("""
<style>
    .stVideo { width: 100% !important; }
    iframe { width: 100% !important; aspect-ratio: 16 / 9; }
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { font-family: 'sans-serif'; }
    [data-testid="stFileUploader"] {
        background-color: #f0f2f6; padding: 1rem; border-radius: 10px; border: 1px dashed #4c78a8;
    }
</style>
""", unsafe_allow_html=True)

def coords_to_zone(lx, ly):
    if pd.isna(lx) or pd.isna(ly): return ""
    if lx < 0 or lx > 9 or ly < 0 or ly > 18: return "Out"
    r = int(min(max(ly, 0), 17.99) // 3)
    c = int(min(max(lx, 0), 8.99) // 3)
    if r < 3: return str([[5,6,1], [7,8,9], [4,3,2]][r][c])
    else: return str([[2,3,4], [1,6,5]][0 if ly < 13.5 else 1][c])

@st.cache_data
def load_data(file_source):
    try:
        df = pd.read_csv(file_source)
        df.columns = [str(c).lower() for c in df.columns]
        
        if 'time_sec' in df.columns:
            df.rename(columns={'time_sec': 'video_time'}, inplace=True)
        
        numeric_cols = ['start_x', 'start_y', 'end_x', 'end_y', 'video_time']
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
                
        if 'video_time' not in df.columns: df['video_time'] = 0
        if 'video_url' not in df.columns: df['video_url'] = ''

        # 180度自動反転（向きの統一）
        # ★ 修正: scout側の保存ロジックと同じ条件にする（sy < 9 のガードを追加）。
        #   これが無いと、scout が既に正規化済みのデータを再度反転してしまい、
        #   始点がfar側(sy>=9)でさらに奥へ向かうプレーが180度ずれる。
        def normalize_direction(row):
            sx, sy = row.get('start_x'), row.get('start_y')
            ex, ey = row.get('end_x'), row.get('end_y')
            
            is_bottom_to_top = False
            if pd.notna(sx) and pd.notna(sy):
                if pd.notna(ex) and pd.notna(ey):
                    if sy < ey and sy < 9: is_bottom_to_top = True   # ★ and sy < 9 を追加
                else:
                    if sy < 9: is_bottom_to_top = True
                    
            if is_bottom_to_top:
                row['start_x'] = 9.0 - sx
                row['start_y'] = 18.0 - sy
                row['start_zone'] = coords_to_zone(row['start_x'], row['start_y'])
                if pd.notna(ex) and pd.notna(ey):
                    row['end_x'] = 9.0 - ex
                    row['end_y'] = 18.0 - ey
                    row['end_zone'] = coords_to_zone(row['end_x'], row['end_y'])
            return row
            
        df = df.apply(normalize_direction, axis=1)
        
        if 'phase' in df.columns: df['phase'] = df['phase'].astype(str).str.upper()
        
        # 背番号やポジションの「.0」を消去して文字列に統一
        target_str_cols = ['set', 'player', 'setter', 'combo', 'pos1', 'pos2', 'pos3', 'pos4', 'pos5', 'pos6']
        for col in target_str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True)
                df[col] = df[col].replace('nan', '')
        
        # セッターの配置からローテーション（S1〜S6）を自動判定する
        def detect_rot_phase(row):
            setter = row.get('setter', '')
            if not setter or setter == 'Direct/Two' or setter == '':
                return 'Unknown'
            for p in ['pos1', 'pos2', 'pos3', 'pos4', 'pos5', 'pos6']:
                if row.get(p) == setter:
                    return p.replace('pos', 'S')
            return 'Unknown'
            
        df['rot_phase'] = df.apply(detect_rot_phase, axis=1)
        
        if 'score' in df.columns:
            try:
                s = df['score'].astype(str).str.split('-', expand=True)
                if s.shape[1]>=2:
                    df['my_score'] = pd.to_numeric(s[0], errors='coerce').fillna(0)
                    df['op_score'] = pd.to_numeric(s[1], errors='coerce').fillna(0)
            except: pass
            
        for col in df.columns:
            if col not in numeric_cols and col not in ['my_score', 'op_score']:
                df[col] = df[col].fillna('').astype(str)
                df[col] = df[col].replace('nan', '')
        return df
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")
        return None

def extract_video_id(url):
    if pd.isna(url) or url == '': return None
    url = str(url)
    match = re.search(r'v=([a-zA-Z0-9_-]{11})', url)
    if match: return match.group(1)
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match: return match.group(1)
    return None

def draw_court(ax, type='normal'):
    ax.add_patch(patches.Rectangle((-3, -3), 15, 24, fc='#e0e0e0', ec='none', zorder=0))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, lw=2, ec='black', fc='#FFCC99', zorder=1))
    
    ax.plot([3,3], [0,18], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=2)
    ax.plot([6,6], [0,18], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=2)
    ax.plot([0,9], [3,3], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=2)
    ax.plot([0,9], [15,15], c='gray', ls=':', lw=1.5, alpha=0.5, zorder=2)
    
    ax.plot([0,9], [9,9], c='red', lw=4, zorder=3)
    ax.plot([0,9], [6,6], c='black', lw=2, zorder=3)
    ax.plot([0,9], [12,12], c='black', lw=2, zorder=3)
    
    ax.set_xlim(-3.5, 12.5)
    ax.set_ylim(-3.5, 13.5)
    ax.set_aspect('equal')
    ax.axis('off')

def create_lineup_img(positions, title=""):
    """ローテ配置図。ネットは下向き（コート下端がネット＝前衛側）。
    positions: {'pos1':名前, ... 'pos6':名前}
    並び（上=後衛、下=前衛/ネット際）:
        後衛: ⑤pos5  ⑥pos6  ①pos1
        前衛: ④pos4  ③pos3  ②pos2
    """
    fig, ax = plt.subplots(figsize=(4, 4.2))
    # コート枠
    ax.add_patch(patches.Rectangle((0, 0), 9, 6, lw=2, ec='black', fc='#FFCC99', zorder=1))
    # ネット（下端を太線で）
    ax.plot([0, 9], [0, 0], c='red', lw=5, zorder=3)
    ax.text(4.5, -0.6, "▼ NET ▼", ha='center', va='top', fontsize=11, fontweight='bold', color='red')
    # アタックライン（前衛と後衛の境界の目安）
    ax.plot([0, 9], [2, 2], c='gray', ls='--', lw=1.2, alpha=0.7, zorder=2)
    # セル区切り（縦）
    ax.plot([3, 3], [0, 6], c='gray', ls=':', lw=1, alpha=0.5, zorder=2)
    ax.plot([6, 6], [0, 6], c='gray', ls=':', lw=1, alpha=0.5, zorder=2)
    ax.plot([0, 9], [3, 3], c='gray', ls=':', lw=1, alpha=0.5, zorder=2)

    circ = {'pos1':'①','pos2':'②','pos3':'③','pos4':'④','pos5':'⑤','pos6':'⑥'}
    # (x中心, y中心, posキー) … 上段=後衛(y=4.5), 下段=前衛(y=1.5)
    layout = [
        (1.5, 4.5, 'pos5'), (4.5, 4.5, 'pos6'), (7.5, 4.5, 'pos1'),
        (1.5, 1.5, 'pos4'), (4.5, 1.5, 'pos3'), (7.5, 1.5, 'pos2'),
    ]
    for cx, cy, pk in layout:
        name = str(positions.get(pk, '') or '—')
        is_server = (pk == 'pos1')
        face = '#ffe1e1' if cy > 3 else '#ffffff'   # 後衛うっすら / 前衛白
        edge = 'red' if is_server else '#555'
        lw = 3 if is_server else 1.2
        ax.add_patch(patches.Rectangle((cx-1.3, cy-1.2), 2.6, 2.4, fc=face, ec=edge, lw=lw, zorder=4))
        ax.text(cx, cy+0.45, circ[pk], ha='center', va='center', fontsize=16, fontweight='bold',
                color='red' if is_server else '#333', zorder=5)
        ax.text(cx, cy-0.45, name, ha='center', va='center', fontsize=13, fontweight='bold', zorder=5)

    if title:
        ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlim(-0.5, 9.5)
    ax.set_ylim(-1.5, 6.8)
    ax.set_aspect('equal')
    ax.axis('off')
    return fig

def get_rotation_positions(rot_df):
    """ローテ該当データから pos1〜pos6 の代表配置を取得（最頻値）。"""
    pos = {}
    for p in ['pos1', 'pos2', 'pos3', 'pos4', 'pos5', 'pos6']:
        if p in rot_df.columns:
            vals = rot_df[p][rot_df[p].astype(str) != '']
            pos[p] = vals.mode().iloc[0] if not vals.empty else ''
        else:
            pos[p] = ''
    return pos

def create_attack_map(data, title):
    kills = len(data[data['quality'].isin(['#', 'T'])])
    rate = (kills / len(data)) * 100 if len(data) > 0 else 0
    
    fig, ax = plt.subplots(figsize=(5, 6.5))
    draw_court(ax, 'attack')
    ax.set_title(f"{title}\n(Kill: {rate:.1f}%)", fontsize=12, fontweight='bold')
    
    for _, r in data.iterrows():
        q = r['quality']
        if q == 'T': c, a = 'gold', 0.9
        elif q == '#': c, a = 'red', 0.8
        elif q in ['/', '^']: c, a = 'gray', 0.7 
        elif q == '-': c, a = 'green', 0.8
        elif q == '"': c, a = 'orange', 0.6
        else: c, a = 'blue', 0.4

        sx, sy = r.get('start_x'), r.get('start_y')
        ex, ey = r.get('end_x'), r.get('end_y')

        if pd.notna(sx) and pd.notna(sy) and pd.notna(ex) and pd.notna(ey):
            dx = ex - sx
            dy = ey - sy
            # ★ 修正: shrink(0.85)を撤廃し、矢印・終点マーカーを真の終点(ex,ey)に一致させる。
            #   従来は85%地点までしか描かず、scout側の終点と一律にずれていた。
            ec = 'black' if c == 'gold' else c
            ax.arrow(sx, sy, dx, dy, width=0.08, head_width=0.3, head_length=0.4,
                     fc=c, ec=ec, alpha=a, length_includes_head=True, zorder=4)
            ax.scatter(ex, ey, color=c, s=15, zorder=5, edgecolors='black', linewidth=0.5)

    return fig

# PDF生成ロジック
def generate_pdf_report(df_analytics, selected_sets, att, rec, fbso_rate, tr_rate, err_rate):
    pdf = FPDF()
    pdf.add_page()
    
    font_path = "ipaexg.ttf"
    has_jp_font = os.path.exists(font_path)
    if has_jp_font:
        pdf.add_font('IPAexGothic', fname=font_path)
        pdf.set_font('IPAexGothic', size=16)
    else:
        pdf.set_font('helvetica', size=16)
        
    sets_str = ", ".join(selected_sets)
    pdf.cell(0, 10, f"Volleyball Analysis Report (Sets: {sets_str})", ln=True, align='C')
    pdf.ln(5)
    
    if has_jp_font: pdf.set_font('IPAexGothic', size=12)
    else: pdf.set_font('helvetica', size=12)
    
    pdf.cell(0, 8, f"FBSO (SideOut 1st Kill): {fbso_rate}", ln=True)
    pdf.cell(0, 8, f"Transition Kill %: {tr_rate}", ln=True)
    pdf.cell(0, 8, f"Attack Error %: {err_rate}", ln=True)
    pdf.ln(5)
    
    if not att.empty:
        fig = create_attack_map(att, "Attack Map (All)")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            fig.savefig(tmpfile.name, format="png", bbox_inches="tight", dpi=150)
            pdf.image(tmpfile.name, x=45, y=pdf.get_y(), w=120)
        os.unlink(tmpfile.name)
        plt.close(fig)
        
    if not att.empty:
        players = sorted(att['player'].dropna().unique())
        if len(players) > 0:
            pdf.add_page()
            if has_jp_font: pdf.set_font('IPAexGothic', size=16)
            pdf.cell(0, 10, "Player-Specific Attack Maps", ln=True, align='C')
            pdf.ln(5)
            
            x_positions = [20, 115]
            img_width = 80
            img_height = 104
            
            current_y = pdf.get_y()
            col = 0
            
            for p in players:
                p_att = att[att['player'] == p]
                if len(p_att) == 0: continue
                
                fig = create_attack_map(p_att, f"{p}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                    fig.savefig(tmpfile.name, format="png", bbox_inches="tight", dpi=150)
                    pdf.image(tmpfile.name, x=x_positions[col], y=current_y, w=img_width)
                os.unlink(tmpfile.name)
                plt.close(fig)
                
                col += 1
                if col > 1:
                    col = 0
                    current_y += img_height + 10
                    if current_y > 270 - img_height:
                        pdf.add_page()
                        current_y = 20

    return bytes(pdf.output())

# ==========================================
# 2. アプリ画面構築
# ==========================================
st.title("🏐 Volleyball Analyst Pro")

with st.sidebar:
    st.header("📂 データ読み込み")
    uploaded_files = st.file_uploader("CSVファイルをアップロード (複数選択可)", type="csv", accept_multiple_files=True)
    df = None
    
    if uploaded_files:
        df_list = []
        for f in uploaded_files:
            sub_df = load_data(f)
            if sub_df is not None:
                df_list.append(sub_df)
        if df_list:
            df = pd.concat(df_list, ignore_index=True)
            st.success(f"✅ {len(uploaded_files)} 個のファイルを統合しました")
    else:
        st.warning("👈 ファイルをアップロードしてください")
    
    if df is not None:
        st.markdown("---")
        st.header("📊 分析対象セット")
        all_sets = sorted(df['set'].unique())
        selected_sets = st.multiselect("セットを選択:", all_sets, default=all_sets)
        if not selected_sets: df_analytics = df.head(0)
        else: df_analytics = df[df['set'].isin(selected_sets)]

if df is not None:
    tab1, tab2 = st.tabs(["🎬 動画検索 (Video)", "📊 ゲーム分析 (Analytics)"])

    with tab1:
        st.markdown("### プレー検索 & 再生")
        with st.expander("🔎 検索条件を設定する", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            def opts(c): return ['All'] + sorted(df[c].unique().tolist())
            with c1:
                f_set = st.selectbox("Set", opts('set'))
                f_ph = st.selectbox("Phase", opts('phase'))
            with c2:
                f_ply = st.selectbox("Player", opts('player'))
                f_skl = st.selectbox("Skill", opts('skill'))
            with c3:
                f_cmb = st.selectbox("Combo", opts('combo'))
                f_qua = st.selectbox("Quality", opts('quality'))
            with c4:
                f_str = st.selectbox("Setter", opts('setter'))

        v_df = df.copy()
        filters = {'set':f_set, 'phase':f_ph, 'player':f_ply, 'skill':f_skl, 'combo':f_cmb, 'quality':f_qua, 'setter':f_str}
        for k, v in filters.items():
            if v != 'All': v_df = v_df[v_df[k]==v]
        
        st.info(f"検索結果: {len(v_df)} 件")
        if len(v_df) > 0:
            for i, row in v_df.head(20).iterrows():
                vid_id = extract_video_id(row.get('video_url', ''))
                t = int(row.get('video_time', 0))
                with st.container():
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.markdown(f"**{row['player']}** - {row['skill']} {row['combo']} ({row['quality']})")
                        if vid_id:
                            link = f"https://www.youtube.com/watch?v={vid_id}&t={t}s"
                            st.markdown(f'<a href="{link}" target="_blank" style="background-color:#ff4b4b;color:white;padding:5px 10px;text-decoration:none;border-radius:5px;">▶ 再生 ({t}s)</a>', unsafe_allow_html=True)
                        else:
                            st.caption("動画リンクがありません")
                    with cols[1]:
                        st.caption(f"Set {row['set']}")
                    st.markdown("---")

    with tab2:
        st.markdown(f"### 📊 分析レポート (Sets: {selected_sets})")
        if len(df_analytics) == 0:
            st.error("データがありません。")
        else:
            att = df_analytics[df_analytics['skill']=='A']
            rec = df_analytics[df_analytics['skill']=='R']
            
            st.subheader("1. スパイクマップ (着地点トラッキング)")
            c1, c2 = st.columns([2, 1])
            with c1:
                if not att.empty: st.pyplot(create_attack_map(att, "Attack (All)"))
                else: st.info("No Attack Data")
            with c2:
                st.markdown("""
                **【Legend】**
                * 🔴 **# (Perfect):** 得点
                * 🟡 **T (BlockOut):** ブロックアウト
                * 🟢 **- (OneTouch):** ワンチ（拾われた）
                * 🔘 **^ または /:** シャット・エラー・リバウンド（グレー）
                * 🟠 **" (Good):** 相手を崩した
                """)

            with st.expander("👤 選手別マップを見る / ダウンロード", expanded=False):
                p_col1, p_col2 = st.columns(2)
                with p_col1: target_player = st.selectbox("選手を選択:", sorted(df['player'].unique()))
                with p_col2:
                    if not att.empty: player_combos = sorted(att[att['player'] == target_player]['combo'].dropna().unique())
                    else: player_combos = []
                    combo_opts = ['All'] + list(player_combos)
                    target_combo = st.selectbox("コンボを選択:", combo_opts)

                p_att = att[att['player'] == target_player]
                if target_combo != 'All': p_att = p_att[p_att['combo'] == target_combo]
                
                if len(p_att) > 0:
                    fig = create_attack_map(p_att, f"{target_player} (Combo: {target_combo})")
                    st.pyplot(fig)
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=300)
                    st.download_button(label=f"📥 このマップ画像をダウンロード", data=buf.getvalue(), file_name=f"AttackMap_{target_player}_{target_combo}.png", mime="image/png")
                else: st.info("条件に合うデータがありません")

            st.markdown("---")
            st.subheader("2. ローテーション別分析 (S1〜S6)")
            st.write("セッターの配置位置から自動判定された各ローテごとの「アタックコース（矢印）」と「攻撃の組み合わせ表」です。サーブ時（ブレイク狙い）とレセプ時（サイドアウト）を分けて分析できます。")

            sel_c1, sel_c2 = st.columns(2)
            with sel_c1:
                # サーブ時 = phase 'S'（自チームサーブ）、レセプ時 = phase 'R'（相手サーブ＝レセプション）
                phase_label = st.radio("局面を選択:", ["レセプ時 (R)", "サーブ時 (S)"], horizontal=True)
                selected_phase = 'R' if phase_label.startswith("レセプ") else 'S'
            with sel_c2:
                selected_rot = st.selectbox("分析するローテーションを選択:", ['S1', 'S6', 'S5', 'S4', 'S3', 'S2'])

            # ローテ × 局面 でフィルタ
            rot_df = df_analytics[(df_analytics['rot_phase'] == selected_rot) & (df_analytics['phase'] == selected_phase)]
            rot_att = rot_df[rot_df['skill'] == 'A']

            tag = f"{selected_rot} / {phase_label}"

            # ★ 選択ローテの選手配置図（ネット下向き＝上側コートが解析対象チーム）
            #    配置は局面に依らず、そのローテ全体(rot_phase一致)から取得
            rot_all = df_analytics[df_analytics['rot_phase'] == selected_rot]
            lineup_src = rot_all if not rot_all.empty else rot_df
            if not lineup_src.empty:
                positions = get_rotation_positions(lineup_src)
                if any(str(v) != '' for v in positions.values()):
                    lc1, lc2 = st.columns([1.0, 1.4])
                    with lc1:
                        st.markdown(f"**【{selected_rot}】 選手配置**")
                        st.pyplot(create_lineup_img(positions, title=f"{selected_rot} Lineup"))
                    with lc2:
                        st.caption("①〜⑥はコート上のローテ位置です。①（赤枠）が現在のサーバー位置。下端がネット側（前衛 ②③④）、上段が後衛（⑤⑥①）。上側コート全体が解析対象チームです。")

            rot_col1, rot_col2 = st.columns([1.2, 1.0])

            with rot_col1:
                st.markdown(f"**【{tag}】 攻撃配球マップ**")
                if not rot_att.empty:
                    rot_fig = create_attack_map(rot_att, f"{selected_rot} ({selected_phase}) Attack Map")
                    st.pyplot(rot_fig)

                    buf_rot = io.BytesIO()
                    rot_fig.savefig(buf_rot, format="png", bbox_inches="tight", dpi=300)
                    st.download_button(label=f"📥 {tag} のマップ画像をダウンロード", data=buf_rot.getvalue(), file_name=f"AttackMap_{selected_rot}_{selected_phase}.png", mime="image/png")
                else:
                    st.info(f"{tag} のアタックデータがまだ記録されていません。")

            with rot_col2:
                st.markdown(f"**【{tag}】 攻撃パターン一覧**")
                if not rot_att.empty:
                    # ★ 1選手1行。コンビ種類は回数つき（例: X5×3, S1×2）で1セルにまとめる
                    def combo_summary(g):
                        counts = g['combo'].value_counts()  # 多い順
                        parts = [f"{combo}×{n}" if n > 1 else f"{combo}" for combo, n in counts.items() if combo != ""]
                        return ", ".join(parts)

                    rot_summary = (
                        rot_att.groupby('player')
                        .apply(combo_summary)
                        .reset_index(name='コンビ種類')
                        .rename(columns={'player': '攻撃選手'})
                    )
                    # 打数が多い選手を上に
                    order = rot_att['player'].value_counts().index.tolist()
                    rot_summary['__order'] = rot_summary['攻撃選手'].apply(lambda p: order.index(p) if p in order else 999)
                    rot_summary = rot_summary.sort_values('__order').drop(columns='__order')

                    st.dataframe(rot_summary, hide_index=True, use_container_width=True)
                else:
                    st.caption("データがありません。")

            st.markdown("---")
            st.subheader("3. チーム基本スタッツ")
            m1, m2 = st.columns(2)
            
            with m1:
                st.markdown("**選手別レセプション成績**")
                if not rec.empty:
                    r_stats = []
                    for p in rec['player'].unique():
                        sub = rec[rec['player']==p]
                        cnt = len(sub)
                        eff = (len(sub[sub['quality'].isin(['#','"'])]) - len(sub[sub['quality']=='^']))/cnt*100 if cnt > 0 else 0
                        r_stats.append({'Player':p, 'Count':cnt, 'Eff%':f"{eff:.1f}"})
                    st.dataframe(pd.DataFrame(r_stats).sort_values('Count', ascending=False), hide_index=True)
                else: st.info("No Reception Data")
                
                st.markdown("**コンビ別決定率 (チーム全体)**")
                if not att.empty:
                    c_stats = []
                    for c in att['combo'].value_counts().index:
                        sub = att[att['combo']==c]
                        if len(sub) == 0: continue
                        k = len(sub[sub['quality'].isin(['#','T'])])
                        c_stats.append({'Combo':c, 'Count':len(sub), 'Kill%':f"{k/len(sub)*100:.1f}"})
                    if c_stats: st.dataframe(pd.DataFrame(c_stats).sort_values('Count', ascending=False), hide_index=True)
                else: st.info("No Attack Data")

            with m2:
                st.markdown("**セッター別サイドアウト率** (Phase: R)")
                if not att.empty and 'setter' in att.columns:
                    k1 = att[att['phase']=='R']
                    if not k1.empty:
                        so = k1.groupby('setter').apply(lambda x: len(x[x['quality'].isin(['#','T'])])/len(x)*100).reset_index(name='SO%')
                        so['SO%'] = so['SO%'].apply(lambda x: f"{x:.1f}")
                        st.dataframe(so, hide_index=True)
                    else: st.caption("No SideOut Data")
                
                st.markdown("**セット別決定率**")
                if not att.empty:
                    sk = att.groupby('set').apply(lambda x: len(x[x['quality'].isin(['#','T'])])/len(x)*100).reset_index(name='Kill%')
                    sk['Kill%'] = sk['Kill%'].apply(lambda x: f"{x:.1f}")
                    st.dataframe(sk, hide_index=True)

            st.markdown("---")
            s1, s2, s3 = st.columns(3)
            fbso_rate = "0.0%"
            if not att.empty and not rec.empty:
                fbso = len(att[(att['phase']=='R') & (att['quality'].isin(['#','T']))])
                if len(rec) > 0: fbso_rate = f"{fbso/len(rec)*100:.1f}%"
            s1.metric("FBSO (SideOut 1st Kill)", fbso_rate)
            
            tr_rate = "0.0%"
            if not att.empty:
                k2 = att[att['phase']=='S']
                if len(k2) > 0:
                    k = len(k2[k2['quality'].isin(['#','T'])])
                    tr_rate = f"{k/len(k2)*100:.1f}%"
            s2.metric("Transition Kill %", tr_rate)
            
            err_rate = "0.0%"
            if not att.empty:
                e = len(att[att['quality']=='^'])
                err_rate = f"{e/len(att)*100:.1f}%"
            s3.metric("Attack Error %", err_rate)
            
            st.markdown("---")
            st.subheader("4. 全体レポートの出力")
            
            if not HAS_FPDF:
                st.error("PDFを出力するには `fpdf2` ライブラリが必要です。")
            else:
                with st.expander("📄 PDFレポートを作成する", expanded=False):
                    if st.button("PDFを生成"):
                        with st.spinner("PDFを生成中..."):
                            pdf_bytes = generate_pdf_report(df_analytics, selected_sets, att, rec, fbso_rate, tr_rate, err_rate)
                            st.session_state['pdf_bytes'] = pdf_bytes
                            st.success("PDFの生成が完了しました！")
                            
                    if 'pdf_bytes' in st.session_state:
                        st.download_button(label="📥 PDFをダウンロード", data=st.session_state['pdf_bytes'], file_name="Volleyball_Analysis_Report.pdf", mime="application/pdf")
