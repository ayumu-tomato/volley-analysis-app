import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from matplotlib import font_manager
import urllib.request
import re
import os

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

@st.cache_data
def load_data(file_source):
    try:
        df = pd.read_csv(file_source)
        df.columns = [str(c).lower() for c in df.columns]
        
        numeric_cols = ['start_x', 'start_y', 'end_x', 'end_y', 'video_time']
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        if 'video_time' not in df.columns: df['video_time'] = 0
        
        if 'phase' in df.columns: df['phase'] = df['phase'].astype(str).str.upper()
        if 'combo' in df.columns: df['combo'] = df['combo'].astype(str)
        
        if 'score' in df.columns:
            try:
                s = df['score'].str.split('-', expand=True)
                if s.shape[1]>=2:
                    df['my_score'] = pd.to_numeric(s[0], errors='coerce').fillna(0)
                    df['op_score'] = pd.to_numeric(s[1], errors='coerce').fillna(0)
            except: pass
            
        for col in df.columns:
            if col not in numeric_cols and col not in ['my_score', 'op_score']:
                df[col] = df[col].fillna('').astype(str)
        return df
    except:
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
    # フリーゾーン (3m)
    ax.add_patch(patches.Rectangle((-3, -3), 15, 24, fc='#e0e0e0', ec='none', zorder=0))
    # コート
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, lw=2, ec='black', fc='#FFCC99', zorder=1))
    ax.plot([0,9], [9,9], c='red', lw=4, zorder=2) # ネット
    ax.plot([0,9], [6,6], c='black', lw=2, zorder=2)
    ax.plot([0,9], [12,12], c='black', lw=2, zorder=2)
    
    # 左右の表示幅
    ax.set_xlim(-3.5, 12.5)
    
    # ★変更点: 分析時に「下半分のコート（着地点）」をメインにフォーカスさせる
    # 下のエンドライン奥（-3.5）から、相手コートのアタックライン奥（13.5）までを表示
    ax.set_ylim(-3.5, 13.5)
        
    ax.set_aspect('equal')
    ax.axis('off')

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
        elif q == '/': c, a = 'black', 0.7
        elif q == '^': c, a = 'black', 0.7
        elif q == '-': c, a = 'green', 0.8
        elif q == '"': c, a = 'orange', 0.6
        else: c, a = 'blue', 0.4

        sx, sy = r.get('start_x'), r.get('start_y')
        ex, ey = r.get('end_x'), r.get('end_y')

        if pd.notna(sx) and pd.notna(sy) and pd.notna(ex) and pd.notna(ey):
            dx = ex - sx
            dy = ey - sy
            shrink = 0.85
            ec = 'black' if c == 'gold' else c
            ax.arrow(sx, sy, dx*shrink, dy*shrink, width=0.08, head_width=0.3, head_length=0.4, 
                     fc=c, ec=ec, alpha=a, length_includes_head=True, zorder=3)
            ax.scatter(sx + dx*shrink, sy + dy*shrink, color=c, s=15, zorder=4, edgecolors='black', linewidth=0.5)

    return fig

# ==========================================
# 2. アプリ画面構築
# ==========================================
st.title("🏐 Volleyball Analyst Pro")

with st.sidebar:
    st.header("📂 データ読み込み")
    uploaded_file = st.file_uploader("CSVファイルをアップロード", type="csv")
    df = None
    
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        st.success(f"✅ {uploaded_file.name} を読み込みました")
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
                    with cols[1]:
                        st.caption(f"Set {row['set']}")
                    st.markdown("---")

    with tab2:
        st.markdown(f"### 📊 分析レポート (Sets: {selected_sets})")
        if len(df_analytics) == 0:
            st.error("データがありません。")
        else:
            att = df_analytics[df_analytics['skill']=='A']
            
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
                * ⚫ **^ または /:** シャット・エラー・リバウンド
                * 🟠 **" (Good):** 相手を崩した
                """)

            with st.expander("👤 選手別マップを見る"):
                target_player = st.selectbox("選手を選択:", sorted(df['player'].unique()))
                p_att = att[att['player']==target_player]
                if len(p_att)>0: st.pyplot(create_attack_map(p_att, target_player))
                else: st.caption("No Attack Data")
