import streamlit as st
import pandas as pd
import sqlite3
import random

# DB初期化
DB_NAME = "flashcards.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            meaning TEXT NOT NULL,
            category TEXT,
            status TEXT DEFAULT '未学習',
            correct_streak INTEGER DEFAULT 0,
            wrong_streak INTEGER DEFAULT 0,
            available_at_step INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_stats (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    # global_stepの初期化
    c.execute("INSERT OR IGNORE INTO system_stats (key, value) VALUES ('global_step', 0)")
    conn.commit()
    conn.close()

def get_global_step():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM system_stats WHERE key='global_step'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def set_global_step(step):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE system_stats SET value=? WHERE key='global_step'", (step,))
    conn.commit()
    conn.close()

# ページ基本設定（レスポンシブ対応）
st.set_page_config(page_title="スマート単語帳", page_icon="📚", layout="centered")
init_db()

# カスタムCSS (スマホ・PC最適化)
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        height: 3.2em;
        font-size: 16px;
        margin-bottom: 8px;
        border-radius: 8px;
    }
    .question-card {
        padding: 20px;
        background-color: #f0f2f6;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 20px;
    }
    .question-word {
        font-size: 32px;
        font-weight: bold;
        color: #1f2937;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📚 スマート単語帳")

menu = st.sidebar.radio("メニュー", ["4択クイズ", "CSVインポート", "単語一覧・管理"])

# ----------------------------------------------------
# 1. 4択クイズ画面
# ----------------------------------------------------
if menu == "4択クイズ":
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 全単語数のカウント
    c.execute("SELECT COUNT(*) FROM words")
    total_words = c.fetchone()[0]
    
    if total_words < 4:
        st.warning("クイズを始めるには最低4つ以上の単語が必要です。「CSVインポート」から登録してください。")
        conn.close()
    else:
        # セッション状態の初期化
        if "session_active" not in st.session_state:
            st.session_state.session_active = False
            st.session_state.session_score = 0
            st.session_state.session_count = 0
            st.session_state.current_word = None
            st.session_state.options = []

        if not st.session_state.session_active:
            st.subheader("🎯 30問クイズセッション")
            st.write(f"登録済みの単語数: **{total_words}** 問")
            if st.button("セッションを開始する（30問）", type="primary"):
                st.session_state.session_active = True
                st.session_state.session_score = 0
                st.session_state.session_count = 0
                st.session_state.current_word = None
                st.rerun()
        else:
            global_step = get_global_step()

            # 30問クリア時
            if st.session_state.session_count >= 30:
                st.balloons()
                st.success(f"🎉 30問のセッションが完了しました！")
                st.metric("今回の正解率", f"{st.session_state.session_score} / 30 問", f"{int(st.session_state.session_score/30*100)}%")
                if st.button("次の30問に挑戦する"):
                    st.session_state.session_count = 0
                    st.session_state.session_score = 0
                    st.session_state.current_word = None
                    st.rerun()
                if st.button("ホームに戻る"):
                    st.session_state.session_active = False
                    st.rerun()
            else:
                # 新しい問題の選出
                if st.session_state.current_word is None:
                    # 出題候補（available_at_step <= global_step）の取得
                    c.execute("""
                        SELECT * FROM words 
                        WHERE available_at_step <= ?
                    """, (global_step,))
                    candidates = c.fetchall()

                    # 候補がない場合は全単語から選出
                    if not candidates:
                        c.execute("SELECT * FROM words")
                        candidates = c.fetchall()

                    # 優先度ソート: 未学習(1) > 忘れがち/うろ覚え(2) > 習得済み/完璧(3)
                    def priority_key(row):
                        status = row[4]
                        if status == '未学習':
                            return 1
                        elif status in ['忘れがち', 'うろ覚え']:
                            return 2
                        else:
                            return 3

                    candidates.sort(key=priority_key)
                    # 同一優先度内からランダム抽出
                    top_priority = priority_key(candidates[0])
                    pool = [w for w in candidates if priority_key(w) == top_priority]
                    chosen = random.choice(pool)
                    st.session_state.current_word = chosen

                    # 誤答ダミー（3択）の選出
                    word_id, word_text, target_meaning, category, *_ = chosen
                    
                    # 同一カテゴリから優先取得
                    c.execute("SELECT meaning FROM words WHERE id != ? AND category = ? ORDER BY RANDOM() LIMIT 3", (word_id, category))
                    dummies = [r[0] for r in c.fetchall()]
                    
                    # 不足している場合は全体から補充
                    if len(dummies) < 3:
                        c.execute("SELECT meaning FROM words WHERE id != ? AND meaning NOT IN ({}) ORDER BY RANDOM() LIMIT ?".format(
                            ','.join(['?']*len(dummies))
                        ), [word_id] + dummies + [3 - len(dummies)])
                        dummies.extend([r[0] for r in c.fetchall()])

                    options = dummies + [target_meaning]
                    random.shuffle(options)
                    st.session_state.options = options

                # クイズUIの描画
                curr = st.session_state.current_word
                progress = st.session_state.session_count / 30.0
                st.progress(progress, text=f"進捗: {st.session_state.session_count + 1} / 30 問")
                
                st.markdown(f"""
                    <div class="question-card">
                        <div style="color: #6b7280; font-size: 14px;">ステータス: {curr[4]}</div>
                        <div class="question-word">{curr[1]}</div>
                    </div>
                """, unsafe_allow_html=True)

                # 4択ボタン
                selected = None
                for opt in st.session_state.options:
                    if st.button(opt):
                        selected = opt

                if selected:
                    correct_meaning = curr[2]
                    curr_id = curr[0]
                    correct_streak = curr[5]
                    wrong_streak = curr[6]

                    new_global_step = global_step + 1
                    set_global_step(new_global_step)

                    if selected == correct_meaning:
                        st.success("⭕ 正解！")
                        st.session_state.session_score += 1
                        new_c_streak = correct_streak + 1
                        new_w_streak = 0
                        new_status = '完璧' if new_c_streak >= 2 else '習得済み'
                        # 正解時は30問先まで除外
                        next_avail = new_global_step + 30

                        c.execute("""
                            UPDATE words SET status=?, correct_streak=?, wrong_streak=?, available_at_step=?
                            WHERE id=?
                        """, (new_status, new_c_streak, new_w_streak, next_avail, curr_id))
                    else:
                        st.error(f"❌ 不正解... (正解: {correct_meaning})")
                        new_c_streak = 0
                        new_w_streak = wrong_streak + 1
                        new_status = '忘れがち' if new_w_streak >= 2 else 'うろ覚え'
                        # 不正解時は1〜10問以内に再出題
                        next_avail = new_global_step + random.randint(1, 10)

                        c.execute("""
                            UPDATE words SET status=?, correct_streak=?, wrong_streak=?, available_at_step=?
                            WHERE id=?
                        """, (new_status, new_c_streak, new_w_streak, next_avail, curr_id))

                    conn.commit()
                    st.session_state.session_count += 1
                    st.session_state.current_word = None
                    st.button("次の問題へ ➡️")

        conn.close()

# ----------------------------------------------------
# 2. CSVインポート画面
# ----------------------------------------------------
elif menu == "CSVインポート":
    st.subheader("📥 CSVファイルから登録")
    st.markdown("`word`, `meaning`, `category` の列が含まれたCSVファイルをアップロードしてください。")

    uploaded_file = st.file_uploader("CSVファイルを選択", type=["csv"])
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.write("プレビュー:", df.head())

            if st.button("データベースに登録", type="primary"):
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                count = 0
                for _, row in df.iterrows():
                    word = str(row['word']).strip()
                    meaning = str(row['meaning']).strip()
                    category = str(row['category']).strip() if 'category' in row and pd.notna(row['category']) else '一般'
                    
                    c.execute("""
                        INSERT INTO words (word, meaning, category)
                        VALUES (?, ?, ?)
                    """, (word, meaning, category))
                    count += 1
                conn.commit()
                conn.close()
                st.success(f"🎉 {count} 件の単語を登録しました！")
        except Exception as e:
            st.error(f"ファイルの読み込みエラー: {e}")

# ----------------------------------------------------
# 3. 単語一覧・管理画面
# ----------------------------------------------------
elif menu == "単語一覧・管理":
    st.subheader("📋 登録済み単語一覧")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT id, word, meaning, category, status, correct_streak, wrong_streak FROM words", conn)
    conn.close()

    if df.empty:
        st.info("登録されている単語はありません。")
    else:
        st.dataframe(df, use_container_width=True)
        st.caption(f"全 {len(df)} 件")
