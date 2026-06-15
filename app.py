import streamlit as st
import pandas as pd
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

        def normalize_direction(row):
            sx, sy = row.get('start_x'), row.get('start_y')
            ex, ey = row.get('end_x'), row.get('end_y')
            
            is_bottom_to_top = False
            if pd.notna(sx) and pd.notna(sy):
                if pd.notna(ex) and pd.notna(ey):
                    if sy < ey: is_bottom_to_top = True
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
        
        # ==============================================================
        # ★ 背番号などが「3.0」になる問題を修正（.0 を切り捨てる）
        # ==============================================================
        for col in ['set', 'player', 'setter', 'combo']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True)
                df[col] = df[col].replace('nan', '') # 空白がnanという文字になるのを防ぐ
        
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
                     fc=c, ec=ec, alpha=a, length_includes_head=True, zorder=4)
            ax.scatter(sx + dx*shrink, sy + dy*shrink, color=c, s=15, zorder=5, edgecolors='black', linewidth=0.5)

    return fig

# ==========================================
# PDF生成ロジック
# ==========================================
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
                * ⚫ **^ または /:** シャット・エラー・リバウンド
                * 🟠 **" (Good):** 相手を崩した
                """)

            with st.expander("👤 選手別マップを見る / ダウンロード", expanded=True):
                p_col1, p_col2 = st.columns(2)
                
                with p_col1:
                    target_player = st.selectbox("選手を選択:", sorted(df['player'].unique()))
                
                with p_col2:
                    if not att.empty:
                        player_combos = sorted(att[att['player'] == target_player]['combo'].dropna().unique())
                    else:
                        player_combos = []
                    combo_opts = ['All'] + list(player_combos)
                    target_combo = st.selectbox("コンボを選択:", combo_opts)

                p_att = att[att['player'] == target_player]
                if target_combo != 'All':
                    p_att = p_att[p_att['combo'] == target_combo]
                    title_suffix = f" (Combo: {target_combo})"
                else:
                    title_suffix = " (All Combos)"

                if len(p_att) > 0:
                    import matplotlib.pyplot as plt
                    fig = create_attack_map(p_att, f"{target_player}{title_suffix}")
                    st.pyplot(fig)
                    
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=300)
                    buf.seek(0)
                    
                    st.download_button(
                        label=f"📥 このマップ画像（{target_player}）をダウンロード",
                        data=buf,
                        file_name=f"AttackMap_{target_player}_{target_combo}.png",
                        mime="image/png"
                    )
                else:
                    st.info("指定された条件（選手・コンボ）のアタックデータがありません。")

            st.markdown("---")
            st.subheader("2. 戦術指標 & スタッツ")
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
                else:
                    st.info("レセプションデータがありません")
                
                st.markdown("**コンビ別決定率**")
                if not att.empty:
                    c_stats = []
                    for c in att['combo'].value_counts().index:
                        sub = att[att['combo']==c]
                        if len(sub) == 0: continue
                        k = len(sub[sub['quality'].isin(['#','T'])])
                        c_stats.append({'Combo':c, 'Count':len(sub), 'Kill%':f"{k/len(sub)*100:.1f}"})
                    if c_stats:
                        st.dataframe(pd.DataFrame(c_stats).sort_values('Count', ascending=False), hide_index=True)
                else:
                    st.info("アタックデータがありません")

            with m2:
                st.markdown("**セッター別サイドアウト率** (Phase: R)")
                if not att.empty and 'setter' in att.columns:
                    k1 = att[att['phase']=='R']
                    if not k1.empty:
                        so = k1.groupby('setter').apply(lambda x: len(x[x['quality'].isin(['#','T'])])/len(x)*100).reset_index(name='SO%')
                        so['SO%'] = so['SO%'].apply(lambda x: f"{x:.1f}")
                        st.dataframe(so, hide_index=True)
                    else:
                        st.caption("レセプションフェイズ(R)の攻撃データがありません")
                
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
            st.subheader("3. レポートの出力")
            
            if not HAS_FPDF:
                st.error("PDFを出力するには `fpdf2` ライブラリが必要です。`requirements.txt` を確認してください。")
            else:
                with st.expander("📄 PDFレポートを作成する", expanded=False):
                    st.write("全体スタッツと選手別のアタックマップを含むPDF形式のレポートを作成します。")
                    if st.button("PDFを生成"):
                        with st.spinner("PDFを生成中...（数秒かかります）"):
                            pdf_bytes = generate_pdf_report(
                                df_analytics, selected_sets, att, rec, 
                                fbso_rate, tr_rate, err_rate
                            )
                            st.session_state['pdf_bytes'] = pdf_bytes
                            st.success("PDFの生成が完了しました！下のボタンからダウンロードしてください。")
                            
                    if 'pdf_bytes' in st.session_state:
                        st.download_button(
                            label="📥 PDFをダウンロード",
                            data=st.session_state['pdf_bytes'],
                            file_name=f"Volleyball_Analysis_Report.pdf",
                            mime="application/pdf"
                        )
