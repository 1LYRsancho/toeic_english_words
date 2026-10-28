import streamlit as st
import pandas as pd
import sqlite3
import random

DB_NAME = "flashcards_v2.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 単語帳（ノートブック）テーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS notebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    # 単語テーブル（どの単語帳に属するかを notebook_id で管理）
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notebook_id INTEGER,
            question TEXT NOT NULL,
            answers TEXT NOT NULL,
            wrongCho TEXT,
            explanation TEXT,
            category TEXT,
            status TEXT DEFAULT '未学習',
            correct_streak INTEGER DEFAULT 0,
            wrong_streak INTEGER DEFAULT 0,
            available_at_step INTEGER DEFAULT 0,
            FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_stats (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
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

st.set_page_config(page_title="スマート単語帳", page_icon="📚", layout="centered")
init_db()

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
        font-size: 26px;
        font-weight: bold;
        color: #1f2937;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📚 スマート単語帳（ファイル管理・統合対応版）")

menu = st.sidebar.radio("メニュー", ["4択クイズ", "CSVインポート", "単語帳の管理・統合"])

# ----------------------------------------------------
# 1. 4択クイズ画面
# ----------------------------------------------------
if menu == "4択クイズ":
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM notebooks")
    notebooks = c.fetchall()
    
    if not notebooks:
        st.warning("単語帳が登録されていません。「CSVインポート」から単語帳を追加してください。")
        conn.close()
    else:
        st.subheader("🎯 4択クイズセッション")
        
        # 学習する単語帳の選択（個別の単語帳、または「すべて統合」）
        nb_options = ["【すべての単語帳を統合して挑戦】"] + [nb[1] for nb in notebooks]
        selected_nb_name = st.selectbox("学習する単語帳を選択", nb_options)
        
        # ターゲットの notebook_id リストを決定
        if selected_nb_name == "【すべての単語帳を統合して挑戦】":
            target_nb_ids = [nb[0] for nb in notebooks]
        else:
            target_nb_ids = [nb[0] for nb in notebooks if nb[1] == selected_nb_name]

        # 該当する単語数をカウント
        placeholders = ','.join(['?'] * len(target_nb_ids))
        c.execute(f"SELECT COUNT(*) FROM words WHERE notebook_id IN ({placeholders})", target_nb_ids)
        total_words = c.fetchone()[0]

        if total_words < 4:
            st.warning("選択した単語帳の登録数が4問未満のため、クイズを開始できません（4問以上必要です）。")
            conn.close()
        else:
            if "session_active" not in st.session_state:
                st.session_state.session_active = False
                st.session_state.session_score = 0
                st.session_state.session_count = 0
                st.session_state.current_word = None
                st.session_state.options = []

            if not st.session_state.session_active:
                st.write(f"対象の単語数: **{total_words}** 問")
                if st.button("セッションを開始する（30問）", type="primary"):
                    st.session_state.session_active = True
                    st.session_state.session_score = 0
                    st.session_state.session_count = 0
                    st.session_state.current_word = None
                    st.rerun()
            else:
                global_step = get_global_step()

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
                    if st.session_state.current_word is None:
                        # 候補取得
                        c.execute(f"""
                            SELECT * FROM words 
                            WHERE notebook_id IN ({placeholders}) AND available_at_step <= ?
                        """, target_nb_ids + [global_step])
                        candidates = c.fetchall()

                        if not candidates:
                            c.execute(f"SELECT * FROM words WHERE notebook_id IN ({placeholders})", target_nb_ids)
                            candidates = c.fetchall()

                        def priority_key(row):
                            status = row[7]
                            if status == '未学習': return 1
                            elif status in ['忘れがち', 'うろ覚え']: return 2
                            else: return 3

                        candidates.sort(key=priority_key)
                        top_priority = priority_key(candidates[0])
                        pool = [w for w in candidates if priority_key(w) == top_priority]
                        chosen = random.choice(pool)
                        st.session_state.current_word = chosen

                        # ダミー選択肢の生成
                        word_id, nb_id, q_text, target_ans, wrong_cho, explanation, category, *_ = chosen
                        
                        dummies = []
                        # wrongChoカラムがあればそこから優先的に抽出
                        if wrong_cho and pd.notna(wrong_cho):
                            dummies = [w.strip() for w in str(wrong_cho).split(';') if w.strip()]
                        
                        # 不足分を同じ単語帳内からランダム補填
                        if len(dummies) < 3:
                            c.execute(f"SELECT answers FROM words WHERE id != ? AND notebook_id IN ({placeholders}) ORDER BY RANDOM() LIMIT ?", [word_id] + target_nb_ids + [3 - len(dummies)])
                            dummies.extend([r[0] for r in c.fetchall()])

                        options = dummies[:3] + [target_ans]
                        random.shuffle(options)
                        st.session_state.options = options

                    curr = st.session_state.current_word
                    progress = st.session_state.session_count / 30.0
                    st.progress(progress, text=f"進捗: {st.session_state.session_count + 1} / 30 問")
                    
                    st.markdown(f"""
                        <div class="question-card">
                            <div style="color: #6b7280; font-size: 13px;">ステータス: {curr[7]}</div>
                            <div class="question-word">{curr[2]}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    selected = None
                    for opt in st.session_state.options:
                        if st.button(opt):
                            selected = opt

                    if selected:
                        correct_ans = curr[3]
                        curr_id = curr[0]
                        correct_streak = curr[8]
                        wrong_streak = curr[9]

                        new_global_step = global_step + 1
                        set_global_step(new_global_step)

                        if selected == correct_ans:
                            st.success("⭕ 正解！")
                            if curr[5] and pd.notna(curr[5]):
                                st.info(f"💡 解説: {curr[5]}")
                            st.session_state.session_score += 1
                            new_c_streak = correct_streak + 1
                            new_w_streak = 0
                            new_status = '完璧' if new_c_streak >= 2 else '習得済み'
                            next_avail = new_global_step + 30

                            c.execute("""
                                UPDATE words SET status=?, correct_streak=?, wrong_streak=?, available_at_step=?
                                WHERE id=?
                            """, (new_status, new_c_streak, new_w_streak, next_avail, curr_id))
                        else:
                            st.error(f"❌ 不正解... (正解: {correct_ans})")
                            if curr[5] and pd.notna(curr[5]):
                                st.info(f"💡 解説: {curr[5]}")
                            new_c_streak = 0
                            new_w_streak = wrong_streak + 1
                            new_status = '忘れがち' if new_w_streak >= 2 else 'うろ覚え'
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
# 2. CSVインポート画面（ファイルごとに分割保存）
# ----------------------------------------------------
elif menu == "CSVインポート":
    st.subheader("📥 CSVファイルから新しい単語帳を作成")
    st.markdown("ファイルごとに独立した単語帳としてインポートできます。")

    notebook_name_input = st.text_input("作成する単語帳の名前（省略するとファイル名になります）")
    uploaded_file = st.file_uploader("CSVファイルを選択", type=["csv"])

    if uploaded_file is not None:
        try:
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8')
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='shift-jis')

            df.columns = df.columns.str.strip()
            
            # カラム名の自動マッピング（英語・日本語対応）
            col_map = {
                'question': 'question', '単語': 'question', 'word': 'question',
                'answers': 'answers', '意味': 'answers', 'meaning': 'answers',
                'wrongCho': 'wrongCho', '誤答': 'wrongCho',
                'explanation': 'explanation', '解説': 'explanation',
                'category': 'category', 'カテゴリ': 'category', 'tags': 'category'
            }
            df = df.rename(columns=col_map)

            if 'question' not in df.columns or 'answers' not in df.columns:
                st.error("エラー: CSVに 'question'（または単語）と 'answers'（または意味）の列が見つかりません。")
                st.write("検出されたカラム:", list(df.columns))
            else:
                st.write("プレビュー:", df.head())
                
                default_name = uploaded_file.name.rsplit('.', 1)[0]
                final_nb_name = notebook_name_input.strip() if notebook_name_input.strip() else default_name

                if st.button("この内容で単語帳を作成する", type="primary"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    
                    # 単語帳を作成（すでに存在する場合は既存IDを利用）
                    c.execute("INSERT OR IGNORE INTO notebooks (name) VALUES (?)", (final_nb_name,))
                    conn.commit()
                    
                    c.execute("SELECT id FROM notebooks WHERE name = ?", (final_nb_name,))
                    nb_id = c.fetchone()[0]

                    count = 0
                    for _, row in df.iterrows():
                        q = str(row['question']).strip()
                        a = str(row['answers']).strip()
                        wc = str(row['wrongCho']).strip() if 'wrongCho' in df.columns and pd.notna(row['wrongCho']) else ''
                        ex = str(row['explanation']).strip() if 'explanation' in df.columns and pd.notna(row['explanation']) else ''
                        cat = str(row['category']).strip() if 'category' in df.columns and pd.notna(row['category']) else '一般'

                        if q and q != 'nan' and a and a != 'nan':
                            c.execute("""
                                INSERT INTO words (notebook_id, question, answers, wrongCho, explanation, category)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (nb_id, q, a, wc, ex, cat))
                            count += 1
                    conn.commit()
                    conn.close()
                    st.success(f"🎉 単語帳「{final_nb_name}」に {count} 件の単語を登録しました！")
        except Exception as e:
            st.error(f"ファイルの読み込みエラー: {e}")

# ----------------------------------------------------
# 3. 単語帳の管理・統合画面
# ----------------------------------------------------
elif menu == "単語帳の管理・統合":
    st.subheader("📋 登録済み単語帳の管理と統合")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM notebooks")
    notebooks = c.fetchall()
    
    if not notebooks:
        st.info("登録されている単語帳はありません。")
        conn.close()
    else:
        # 単語帳ごとの単語数を表示
        nb_data = []
        for nb_id, nb_name in notebooks:
            c.execute("SELECT COUNT(*) FROM words WHERE notebook_id = ?", (nb_id,))
            cnt = c.fetchone()[0]
            nb_data.append({"ID": nb_id, "単語帳名": nb_name, "登録単語数": cnt})
        
        df_nb = pd.DataFrame(nb_data)
        st.dataframe(df_nb, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🔗 単語帳の統合（マージ）")
        st.write("複数の単語帳を1つにまとめて新しい単語帳を作成できます。")
        
        nb_names = [nb[1] for nb in notebooks]
        if len(nb_names) >= 2:
            sources = st.multiselect("統合したい単語帳を複数選択してください", nb_names)
            new_merged_name = st.text_input("統合後の新しい単語帳の名前")
            
            if st.button("選択した単語帳を統合する", type="primary"):
                if not new_merged_name.strip():
                    st.error("統合後の新しい単語帳名を入力してください。")
                elif len(sources) < 2:
                    st.error("統合するには2つ以上の単語帳を選択してください。")
                else:
                    try:
                        # 新しい統合先単語帳を作成
                        c.execute("INSERT OR IGNORE INTO notebooks (name) VALUES (?)", (new_merged_name.strip(),))
                        conn.commit()
                        c.execute("SELECT id FROM notebooks WHERE name = ?", (new_merged_name.strip(),))
                        new_id = c.fetchone()[0]
                        
                        # 選択された単語帳に属するすべての単語の notebook_id を新しいIDに付け替える（またはコピーする）
                        # ここでは安全にデータをコピーする形にします
                        total_moved = 0
                        for src_name in sources:
                            c.execute("SELECT id FROM notebooks WHERE name = ?", (src_name,))
                            src_id = c.fetchone()[0]
                            
                            c.execute("""
                                UPDATE words SET notebook_id = ? WHERE notebook_id = ?
                            """, (new_id, src_id))
                            total_moved += c.rowcount
                            
                            # 空になった元の単語帳を削除する場合
                            c.execute("DELETE FROM notebooks WHERE id = ?", (src_id,))
                        
                        conn.commit()
                        st.success(f"🎉 統合完了！新しい単語帳「{new_merged_name}」に {total_moved} 件の単語をまとめました。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"統合エラー: {e}")
        else:
            st.info("統合を行うには、少なくとも2つ以上の単語帳が必要です。")
            
        conn.close()
