import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
# import japanize_matplotlib  <-- これを削除
from matplotlib import font_manager # <-- 追加
import urllib.request # <-- 追加
from matplotlib.lines import Line2D
import re
import os


# ==========================================
# 0. 日本語フォント設定 (japanize_matplotlibの代わり)
# ==========================================
def init_japanese_font():
    # IPAexGothicフォントをダウンロードして設定
    font_path = "ipaexg.ttf"
    if not os.path.exists(font_path):
        # フォントファイルのURL (GitHubのミラーなどから取得)
        url = "https://github.com/minoryorg/ipaexg/raw/master/ipaexg.ttf"
        try:
            urllib.request.urlretrieve(url, font_path)
        except:
            return # ダウンロード失敗時は英語のまま
            
    if os.path.exists(font_path):
        font_manager.fontManager.addfont(font_path)
        plt.rcParams['font.family'] = 'IPAexGothic'


# アプリ起動時にフォントを設定
init_japanese_font()


# ==========================================
# 1. 設定 & 関数定義
# ==========================================
st.set_page_config(page_title="Volleyball Analyst Pro", layout="wide")


# CSS調整
st.markdown("""
<style>
    .stVideo { width: 100% !important; }
    iframe { width: 100% !important; aspect-ratio: 16 / 9; }
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { font-family: 'sans-serif'; }
    /* サイドバーのアップローダーを目立たせる */
    [data-testid="stFileUploader"] {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border: 1px dashed #4c78a8;
    }
</style>
""", unsafe_allow_html=True)


# --- データ読み込み関数 ---
@st.cache_data
def load_data(file_source):
    try:
        df = pd.read_csv(file_source)
        df.columns = [str(c).lower() for c in df.columns]
        
        # 列名マッピング (L=video_url, M=video_time)
        cols = list(df.columns)
        rename_map = {}
        if len(cols) > 11: rename_map[cols[11]] = 'video_url'
        if len(cols) > 12: rename_map[cols[12]] = 'video_time'
        if rename_map: df.rename(columns=rename_map, inplace=True)


        # 型変換
        if 'video_time' in df.columns:
            df['video_time'] = pd.to_numeric(df['video_time'], errors='coerce').fillna(0).astype(int)
        else:
            df['video_time'] = 0
        
        if 'phase' in df.columns: df['phase'] = df['phase'].astype(str).str.upper()
        if 'combo' in df.columns: df['combo'] = df['combo'].astype(str)
        
        # スコア分割
        if 'score' in df.columns:
            try:
                s = df['score'].str.split('-', expand=True)
                if s.shape[1]>=2:
                    df['my_score'] = pd.to_numeric(s[0], errors='coerce').fillna(0)
                    df['op_score'] = pd.to_numeric(s[1], errors='coerce').fillna(0)
            except: pass
            
        for col in df.columns:
            if col not in ['video_time', 'my_score', 'op_score']:
                df[col] = df[col].fillna('').astype(str)
        return df
    except:
        return None


# --- 動画ID抽出 ---
def extract_video_id(url):
    if pd.isna(url) or url == '': return None
    url = str(url)
    match = re.search(r'v=([a-zA-Z0-9_-]{11})', url)
    if match: return match.group(1)
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match: return match.group(1)
    return None


# --- コート描画関連 ---
def get_x_from_combo(combo, start_zone):
    # スロット定義
    slot_map = {'5': 0.5, '4': 1.5, '3': 2.5, '2': 3.5, '1': 4.5, '0': 5.5, 'A': 6.5, 'B': 7.5, 'C': 8.5}
    if start_zone in ['4','5','7']: def_x = 1.5
    elif start_zone in ['2','1','9']: def_x = 7.5
    else: def_x = 4.5
    if combo == '' or combo == 'nan': return def_x
    char = str(combo).strip()[-1].upper()
    return slot_map.get(char, def_x)


opponent_coords = {
    '1': (1.5, 7.5), '6': (4.5, 7.5), '5': (7.5, 7.5),
    '9': (1.5, 4.5), '8': (4.5, 4.5), '7': (7.5, 4.5),
    '2': (1.5, 1.5), '3': (4.5, 1.5), '4': (7.5, 1.5)
}
zone_coords = {
    '1':(7.5,1.5), '6':(4.5,1.5), '5':(1.5,1.5), '9':(7.5,4.5), '8':(4.5,4.5), '7':(1.5,4.5), 
    '2':(7.5,7.5), '3':(4.5,7.5), '4':(1.5,7.5)
}


def draw_court(ax, type='normal'):
    h = 18 if type=='serve' else 9
    court = patches.Rectangle((0, 0), 9, h, lw=2, ec='black', fc='#FFCC99')
    ax.add_patch(court)
    
    if type == 'attack':
        ax.plot([0,9], [0,0], c='red', lw=4) # Net Bottom
        ax.plot([0,9], [3,3], c='black', lw=2)
        ax.text(4.5, -0.8, "NET (Slots)", ha='center', fontsize=8, color='red')
        ax.set_ylim(-1, 10)
    elif type == 'serve':
        ax.plot([0,9], [9,9], c='red', lw=3)
        ax.plot([0,9], [6,6], c='black', lw=2)
        ax.plot([0,9], [12,12], c='black', lw=2)
        ax.set_ylim(-2, 20)
    else: # normal
        ax.plot([0,9], [9,9], c='red', lw=4)
        ax.plot([0,9], [6,6], c='black', lw=2)
        ax.set_ylim(-1, 10)
        
    ax.set_xlim(-1, 10)
    ax.set_aspect('equal')
    ax.axis('off')


# --- マップ作成関数 ---
def create_attack_map(data, title):
    kills = len(data[data['quality'].isin(['#', 'T'])])
    rate = (kills / len(data)) * 100 if len(data) > 0 else 0
    
    fig, ax = plt.subplots(figsize=(5, 5))
    draw_court(ax, 'attack')
    ax.set_title(f"{title}\n(Kill: {rate:.1f}%)", fontsize=10, fontweight='bold')
    
    data = data.copy()
    if 'end_zone' not in data.columns: data['end_zone'] = -1
    data['end_zone'] = data['end_zone'].replace('', -1).fillna(-1)


    grp = data.groupby(['start_zone', 'end_zone', 'combo', 'quality']).size().reset_index(name='count')
    
    for _, r in grp.iterrows():
        s, e, c_val, q, cnt = str(r['start_zone']).replace('.0',''), str(r['end_zone']).replace('.0',''), r['combo'], r['quality'], r['count']
        sx = get_x_from_combo(c_val, s); sy = 0.0
        
        if q=='T': c,ls,a='green','-',0.9
        elif q=='#': c,ls,a='red','-',1.0
        elif q=='^': c,ls,a='black',':',0.6
        else: c,ls,a='blue','-',0.4
        
        # ブロックアウト or エンドゾーンなし -> 点
        if q=='T' or e not in opponent_coords:
            m = 's' if q=='T' else ('x' if q=='^' else 'o')
            ax.scatter(sx, sy, s=cnt*100, c=c, marker=m, alpha=a, edgecolors='white')
        else:
            ex, ey = opponent_coords[e]
            if q=='#': ex+=0.2
            elif q=='^': ex-=0.2
            width = 0.04 + (cnt * 0.05)
            ax.arrow(sx, sy, ex-sx, ey-sy, width=width, color=c, linestyle=ls, alpha=a, length_includes_head=True)
            
    return fig


def create_reception_map(data, title):
    succ = len(data[data['quality'].isin(['#', '"'])])
    rate = succ/len(data)*100 if len(data)>0 else 0
    
    fig, ax = plt.subplots(figsize=(5, 5))
    draw_court(ax, 'normal')
    ax.set_title(f"{title}\n(Succ: {rate:.1f}%)", fontsize=10, fontweight='bold')
    
    zones = data['start_zone'].unique()
    for z in zones:
        z_str = str(z).replace('.0','')
        if z_str not in zone_coords: continue
        bx, by = zone_coords[z_str]
        
        sub = data[data['start_zone']==z]
        total = len(sub)
        counts = sub['quality'].value_counts()
        p = [counts.get('#',0), counts.get('"',0), counts.get('^',0)]
        p.append(total - sum(p))
        cols = ['red', 'orange', 'black', 'skyblue']
        
        radius = 0.2 + (np.sqrt(total) * 0.1)
        curr_ang = 90
        for val, col in zip(p, cols):
            if val==0: continue
            ang = (val/total)*360
            w = patches.Wedge((bx,by), radius, curr_ang-ang, curr_ang, fc=col, ec='white', alpha=0.8)
            ax.add_patch(w)
            curr_ang -= ang
        ax.text(bx, by, str(total), ha='center', va='center', color='white', fontsize=8, fontweight='bold', bbox=dict(boxstyle="circle,pad=0.1", fc="gray", ec="none", alpha=0.5))
    return fig


def create_serve_map(data, title):
    fig, ax = plt.subplots(figsize=(5, 8))
    draw_court(ax, 'serve')
    ax.set_title(title, fontsize=10, fontweight='bold')
    
    start_m = {'1':(8,-0.5),'6':(4.5,-0.5),'5':(1,-0.5)}
    end_m = {'1':(1.5,16.5),'6':(4.5,16.5),'5':(7.5,16.5),'2':(1.5,10.5),'3':(4.5,10.5),'4':(7.5,10.5),'9':(1.5,13.5),'8':(4.5,13.5),'7':(7.5,13.5)}
    
    grp = data.groupby(['start_zone','end_zone','quality']).size().reset_index(name='count')
    for _, r in grp.iterrows():
        s, e, q, c = str(r['start_zone']).replace('.0',''), str(r['end_zone']).replace('.0',''), r['quality'], r['count']
        if e in end_m:
            sx, sy = start_m.get(s, (4.5,-0.5))
            ex, ey = end_m[e]
            if q=='#': col='red'; ls='-'; off=0.2; alp=1.0
            elif q=='"': col='orange'; ls='-'; off=0.0; alp=0.8
            elif q=='^': col='black'; ls=':'; off=-0.2; alp=0.5
            else: col='blue'; ls='-'; off=0.0; alp=0.5
            ex+=off
            ax.arrow(sx, sy, ex-sx, ey-sy, width=0.03+c*0.04, color=col, ls=ls, alpha=alp, length_includes_head=True)
    return fig


# ==========================================
# 2. アプリ画面構築
# ==========================================
st.title("🏐 Volleyball Analyst Pro")


# --- Sidebar ---
with st.sidebar:
    st.header("📂 データ読み込み")
    uploaded_file = st.file_uploader("CSVファイルをアップロード", type="csv")
    
    df = None
    # デフォルトファイル設定 (GitHubリポジトリ内のパス)
    default_file = 'volleyball_data_with_time.csv'
    
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        st.success(f"✅ {uploaded_file.name} を読み込みました")
    elif os.path.exists(default_file):
        df = load_data(default_file)
        st.info(f"ℹ️ デフォルトデータを使用中")
    else:
        st.warning("👈 ファイルをアップロードしてください")
    
    if df is not None:
        st.markdown("---")
        st.header("📊 分析対象セット")
        all_sets = sorted(df['set'].unique())
        selected_sets = st.multiselect("セットを選択:", all_sets, default=all_sets)
        
        if not selected_sets:
            st.warning("セットを選択してください")
            df_analytics = df.head(0)
        else:
            df_analytics = df[df['set'].isin(selected_sets)]


# --- Main Tabs ---
if df is not None:
    tab1, tab2 = st.tabs(["🎬 動画検索 (Video)", "📊 ゲーム分析 (Analytics)"])


    # ==========================================
    # TAB 1: 動画検索
    # ==========================================
    with tab1:
        st.markdown("### プレー検索 & 再生")
        with st.expander("🔎 検索条件を設定する", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            def opts(c): return ['All'] + sorted(df[c].unique().tolist())
            
            with c1:
                f_set = st.selectbox("Set", opts('set'), key='v_set')
                f_ph = st.selectbox("Phase", opts('phase'), key='v_ph')
                f_start = st.selectbox("Start Zone", opts('start_zone'), key='v_st')
            with c2:
                f_ply = st.selectbox("Player", opts('player'), key='v_pl')
                f_skl = st.selectbox("Skill", opts('skill'), key='v_sk')
                f_end = st.selectbox("End Zone", opts('end_zone'), key='v_ed')
            with c3:
                f_cmb = st.selectbox("Combo", opts('combo'), key='v_cmb')
                f_qua = st.selectbox("Quality", opts('quality'), key='v_qa')
            with c4:
                f_str = st.selectbox("Setter", opts('setter'), key='v_str')
                f_scr = st.selectbox("Score", opts('score'), key='v_scr')


        v_df = df.copy()
        filters = {
            'set':f_set, 'phase':f_ph, 'player':f_ply, 'skill':f_skl, 
            'combo':f_cmb, 'quality':f_qua, 'setter':f_str, 'score':f_scr,
            'start_zone':f_start, 'end_zone':f_end
        }
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
                            st.caption("動画IDなし")
                    with cols[1]:
                        st.caption(f"Set {row['set']} | {row['score']}")
                    st.markdown("---")


    # ==========================================
    # TAB 2: ゲーム分析
    # ==========================================
    with tab2:
        st.markdown(f"### 📊 分析レポート (Sets: {selected_sets})")
        
        if len(df_analytics) == 0:
            st.error("データがありません。")
        else:
            att = df_analytics[df_analytics['skill']=='A']
            rec = df_analytics[df_analytics['skill']=='R']
            srv = df_analytics[df_analytics['skill']=='S']


            st.subheader("1. マップ分析 (全体)")
            c1, c2, c3 = st.columns(3)
            with c1:
                if not att.empty: st.pyplot(create_attack_map(att, "Attack (All)"))
                else: st.info("No Attack Data")
            with c2:
                if not rec.empty: st.pyplot(create_reception_map(rec, "Reception (All)"))
                else: st.info("No Reception Data")
            with c3:
                if not srv.empty: st.pyplot(create_serve_map(srv, "Serve (All)"))
                else: st.info("No Serve Data")


            with st.expander("👤 選手別マップを見る"):
                target_player = st.selectbox("選手を選択:", sorted(df['player'].unique()))
                pc1, pc2, pc3 = st.columns(3)
                p_att = att[att['player']==target_player]
                p_rec = rec[rec['player']==target_player]
                p_srv = srv[srv['player']==target_player]
                
                with pc1:
                    if len(p_att)>0: st.pyplot(create_attack_map(p_att, target_player))
                    else: st.caption("No Attack")
                with pc2:
                    if len(p_rec)>0: st.pyplot(create_reception_map(p_rec, target_player))
                    else: st.caption("No Reception")
                with pc3:
                    if len(p_srv)>0: st.pyplot(create_serve_map(p_srv, target_player))
                    else: st.caption("No Serve")


            st.subheader("2. 戦術指標 & スタッツ")
            m1, m2 = st.columns(2)
            with m1:
                st.markdown("**選手別レセプション成績**")
                if not rec.empty:
                    r_stats = []
                    for p in rec['player'].unique():
                        sub = rec[rec['player']==p]
                        cnt = len(sub)
                        eff = (len(sub[sub['quality'].isin(['#','"'])]) - len(sub[sub['quality']=='^']))/cnt*100
                        r_stats.append({'Player':p, 'Count':cnt, 'Eff%':f"{eff:.1f}"})
                    st.dataframe(pd.DataFrame(r_stats).sort_values('Count', ascending=False), hide_index=True)
                
                st.markdown("**コンビ別決定率**")
                if not att.empty:
                    c_stats = []
                    for c in att['combo'].value_counts().index:
                        sub = att[att['combo']==c]
                        k = len(sub[sub['quality'].isin(['#','T'])])
                        c_stats.append({'Combo':c, 'Count':len(sub), 'Kill%':f"{k/len(sub)*100:.1f}"})
                    st.dataframe(pd.DataFrame(c_stats), hide_index=True)


            with m2:
                st.markdown("**セッター別サイドアウト率** (Phase: R)")
                if not att.empty and 'setter' in att.columns:
                    k1 = att[att['phase']=='R']
                    if not k1.empty:
                        so = k1.groupby('setter').apply(lambda x: len(x[x['quality'].isin(['#','T'])])/len(x)*100).reset_index(name='SO%')
                        so['SO%'] = so['SO%'].apply(lambda x: f"{x:.1f}")
                        st.dataframe(so, hide_index=True)
                
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
                fbso_rate = f"{fbso/len(rec)*100:.1f}%"
            s1.metric("FBSO (SideOut 1st Kill)", fbso_rate)
            
            tr_rate = "0.0%"
            if not att.empty:
                k2 = att[att['phase']=='S']
                if len(k2)>0:
                    k = len(k2[k2['quality'].isin(['#','T'])])
                    tr_rate = f"{k/len(k2)*100:.1f}%"
            s2.metric("Transition Kill %", tr_rate)
            
            err_rate = "0.0%"
            if not att.empty:
                e = len(att[att['quality']=='^'])
                err_rate = f"{e/len(att)*100:.1f}%"
            s3.metric("Attack Error %", err_rate)
else:
    st.info("👈 サイドバーからデータをアップロードしてください")