import os
import json
import re
import xml.etree.ElementTree as ET
import streamlit as st
import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def get_secret(key, default=""):
    val = ""
    if hasattr(st, "secrets") and key in st.secrets:
        val = str(st.secrets[key])
    else:
        val = str(os.getenv(key, default))
    return val.strip().strip("'").strip('"')

SUPABASE_URL = get_secret("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = get_secret("SUPABASE_KEY", "")
DEFAULT_GEMINI_KEY = get_secret("GEMINI_API_KEY", "")

# Авторизация
AUTH_USERS = {"slava": "slava2026", "teamlead": "picslead2026"}
if hasattr(st, "secrets") and "AUTH_USERS" in st.secrets:
    try:
        sec_auth = st.secrets["AUTH_USERS"]
        if hasattr(sec_auth, "items"):
            AUTH_USERS.update({str(k).lower().strip(): str(v).strip() for k, v in sec_auth.items()})
        elif isinstance(sec_auth, str) and sec_auth.strip():
            parsed = json.loads(sec_auth.replace("'", '"'))
            AUTH_USERS.update({str(k).lower().strip(): str(v).strip() for k, v in parsed.items()})
    except Exception:
        pass

st.set_page_config(page_title="SEO RAG Enterprise Hub", layout="wide", page_icon="🎯", initial_sidebar_state="expanded")

# --- CUSTOM CSS (Adaptive SaaS Navigation & Branding) ---
st.markdown("""
<style>
    /* Выравниваем текст всех кнопок в сайдбаре по левому краю */
    [data-testid="stSidebar"] .stButton > button {
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
    
    /* Фирменные желтые кнопки (Primary) */
    .stButton > button[kind="primary"] {
        background-color: #FFC107 !important; 
        color: #000000 !important; 
        border: none !important; 
        font-weight: 700 !important; 
        border-radius: 8px !important; 
        transition: all 0.2s ease;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #E0A800 !important; 
        color: #000000 !important;
        transform: translateY(-1px); 
    }
    
    /* Неактивные кнопки: адаптивный цвет под любую тему */
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background-color: transparent !important; 
        color: var(--text-color) !important; 
        border: 1px solid transparent !important; 
        font-weight: 500 !important;
        border-radius: 8px !important;
        opacity: 0.85;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background-color: rgba(128, 128, 128, 0.12) !important; 
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        opacity: 1;
    }
    
    /* Адаптивные цветные бейджи для темной и светлой темы */
    .badge-green { background-color: rgba(46, 133, 64, 0.2); color: #2E7D32; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(46, 133, 64, 0.4); }
    .badge-yellow { background-color: rgba(245, 158, 11, 0.2); color: #D97706; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-red { background-color: rgba(239, 68, 68, 0.2); color: #DC2626; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-neutral { background-color: rgba(128, 128, 128, 0.15); color: var(--text-color); padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; }
    
    /* Скругляем логотипы */
    [data-testid="stSidebar"] [data-testid="stImage"] img {
        border-radius: 16px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
    }
</style>
""", unsafe_allow_html=True)

def get_score_badge(score):
    if score >= 0.65: return f"<span class='badge-green'>Score: {score:.2f}</span>"
    elif score >= 0.45: return f"<span class='badge-yellow'>Score: {score:.2f}</span>"
    else: return f"<span class='badge-red'>Score: {score:.2f}</span>"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None

if not st.session_state["authenticated"]:
    with st.container(border=True):
        st.markdown("### 🔐 Авторизация в SEO RAG Hub")
        col1, _ = st.columns([1, 2])
        with col1:
            user_input = st.text_input("Логин")
            pass_input = st.text_input("Пароль", type="password")
            if st.button("Войти", type="primary"):
                u = user_input.strip().lower()
                p = pass_input.strip()
                if u in AUTH_USERS and AUTH_USERS[u] == p:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = u
                    st.rerun()
                else:
                    st.error("Неверный логин или пароль")
    st.stop()

# --- САЙДБАР ---
with st.sidebar:
    st.write("") 
    
    if "selected_product" not in st.session_state:
        st.session_state.selected_product = "pics.io"
        
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        try:
            if st.session_state.selected_product == "pics.io":
                st.image("picsio_logo.jpeg", use_container_width=True)
            else:
                st.image("toriut_logo.jpeg", use_container_width=True)
        except Exception:
            pass
            
    st.write("") 
    
    selected_product = st.selectbox(
        "Продукт",
        options=["pics.io", "toriut"],
        format_func=lambda x: "Pics.io (DAM)" if x == "pics.io" else "Toriut (PIM)",
        key="selected_product",
        label_visibility="collapsed"
    )
        
    st.divider()

    st.markdown(f"👤 **Пользователь:** <span class='badge-neutral'>{st.session_state['username']}</span>", unsafe_allow_html=True)
    if st.button("🚪 Выйти", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    
    st.write("")
    st.markdown("<p style='opacity: 0.7; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:10px;'>MODULES</p>", unsafe_allow_html=True)
    
    # --- НАТИВНАЯ КНОПОЧНАЯ НАВИГАЦИЯ ---
    menu_items = [
        "✍️ Генерация + Доктор",
        "📊 Gap Audit",
        "⚙️ Data Manager",
        "🔗 Линк-билдер",
        "⚡ Batch Processing",
        "📜 История"
    ]
    
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = menu_items[0]
        
    for item in menu_items:
        btn_type = "primary" if st.session_state.active_tab == item else "secondary"
        if st.button(item, key=f"nav_{item}", use_container_width=True, type=btn_type):
            st.session_state.active_tab = item
            st.rerun()
    
    st.divider()
    
    st.markdown("<p style='opacity: 0.7; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:0px;'>SETTINGS</p>", unsafe_allow_html=True)
    gemini_key_input = st.text_input("Gemini API Key", value=DEFAULT_GEMINI_KEY, type="password")
    CURRENT_KEY = gemini_key_input.strip().strip("'").strip('"')

@st.cache_data(ttl=3600, show_spinner=False)
def resolve_models(api_key):
    if not api_key: return None, None, "Укажите Gemini API Key"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            models_data = res.json().get("models", [])
            embed_cands = [m["name"] for m in models_data if "embedContent" in m.get("supportedGenerationMethods", [])]
            gen_cands = [m["name"] for m in models_data if "generateContent" in m.get("supportedGenerationMethods", [])]

            embed_m = None
            for pref in ["text-embedding-004", "embedding-001", "gemini-embedding"]:
                for c in embed_cands:
                    if pref in c: embed_m = c; break
                if embed_m: break
            if not embed_m and embed_cands: embed_m = embed_cands[0]

            gen_m = None
            for pref in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.0-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                for c in gen_cands:
                    if pref in c: gen_m = c; break
                if gen_m: break
            if not gen_m:
                for c in gen_cands:
                    if "flash" in c: gen_m = c; break
            if not gen_m and gen_cands: gen_m = gen_cands[0]

            return embed_m or "models/text-embedding-004", gen_m or "models/gemini-1.5-flash", "OK"
        else: return None, None, f"Код ошибки: {res.status_code}"
    except Exception as e: return "models/text-embedding-004", "models/gemini-1.5-flash", f"Fallback: {e}"

EMBED_MODEL, GEN_MODEL, KEY_STATUS = resolve_models(CURRENT_KEY)

with st.sidebar:
    if KEY_STATUS == "OK":
        st.markdown(f"""
        <div style='background-color: rgba(128, 128, 128, 0.08); padding: 10px; border-radius: 8px; border: 1px solid rgba(128, 128, 128, 0.2); font-size: 0.85em; color: var(--text-color);'>
            <span style='color: #2E7D32;'>●</span> <b>Connected</b><br>
            <span style='opacity: 0.7;'>Search:</span> {EMBED_MODEL.replace('models/', '')}<br>
            <span style='opacity: 0.7;'>Gen:</span> {GEN_MODEL.replace('models/', '')}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error(f"⚠️ {KEY_STATUS}")

# --- API ФУНКЦИИ ---
def get_supabase_headers(): 
    return {
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}", 
        "Content-Type": "application/json"
    }

def get_embedding(text: str):
    if not CURRENT_KEY or not EMBED_MODEL: return None
    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent?key={CURRENT_KEY}", 
            json={"content": {"parts": [{"text": text}]}}, 
            timeout=10
        )
        if res.status_code == 200: 
            return res.json()["embedding"]["values"][:768]
    except Exception: 
        pass
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_KEY or not GEN_MODEL: return "Ошибка: API Key."
    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/{GEN_MODEL}:generateContent?key={CURRENT_KEY}", 
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}, 
            timeout=30
        )
        if res.status_code == 200: 
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"⚠️ Ошибка ({res.status_code}): {res.json().get('error', {}).get('message', '')}"
    except Exception as e: 
        return f"⚠️ Ошибка: {e}"

def retrieve_facts(query: str, product: str, top_k: int = 6, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: 
        return []
    
    if product == "toriut":
        rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/match_toriut_facts"
        payload = {
            "query_embedding": vec,
            "match_threshold": threshold,
            "match_count": top_k
        }
    else:
        rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/match_facts"
        payload = {
            "query_embedding": vec,
            "match_threshold": threshold,
            "match_count": top_k,
            "filter_product": product
        }
        
    try:
        res = requests.post(rpc_url, headers=get_supabase_headers(), json=payload, timeout=10)
        if res.status_code == 200: 
            return res.json()
    except Exception: 
        pass
    return []

def retrieve_linking_pages(query: str, product: str, top_k: int = 4, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: 
        return []
    try:
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/match_site_pages", 
            headers=get_supabase_headers(), 
            json={"query_embedding": vec, "match_threshold": threshold, "match_count": top_k, "filter_product": product}, 
            timeout=10
        )
        if res.status_code == 200: 
            return res.json()
    except Exception: 
        pass
    return []

def save_generation_to_history(product, author, kw, content_type, text, verdict):
    url = f"{SUPABASE_URL}/rest/v1/content_history"
    headers = get_supabase_headers()
    headers["Prefer"] = "return=minimal"
    payload = {
        "product": product,
        "author": author,
        "target_keyword": kw,
        "content_type": content_type,
        "generated_text": text,
        "doctor_verdict": verdict,
        "status": "PASS" if "PASS" in str(verdict).upper() else "FAIL"
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception:
        pass

def get_content_history(product: str):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/content_history?product=eq.{product}&order=created_at.desc&limit=20", 
            headers=get_supabase_headers(), 
            timeout=8
        )
        if res.status_code == 200: 
            return res.json()
    except Exception: 
        pass
    return []

# --- MAIN CONTENT AREA ---
st.title(st.session_state.active_tab.split(" (")[0])

# 1. ГЕНЕРАЦИЯ + ДОКТОР
if st.session_state.active_tab.startswith("✍️ Генерация"):
    with st.container(border=True):
        st.markdown("#### SEO параметры")
        col1, col2 = st.columns([1, 1])
        default_kw = "Toriut Shopify integration features" if selected_product == "toriut" else "Google Drive DAM integration features"
        with col1: 
            target_kw = st.text_input("Целевой ключевой запрос", value=default_kw)
        with col2: 
            content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        c1, c2 = st.columns(2)
        with c1: 
            top_k = st.slider("Количество фактов из базы", 2, 12, 6)
        with c2: 
            top_links_count = st.slider("Количество внутренних ссылок", 1, 6, 3)
            
        run_btn = st.button("🚀 Сгенерировать контент", type="primary", use_container_width=True)

    if run_btn and target_kw:
        st.divider()
        with st.spinner("Сбор данных из векторной базы..."):
            facts = retrieve_facts(target_kw, selected_product, top_k=top_k)
            pages = retrieve_linking_pages(target_kw, selected_product, top_k=top_links_count)
            
        c_left, c_right = st.columns([1.2, 2])
        with c_left:
            with st.container(border=True):
                st.markdown(f"**📚 Извлеченные факты ({len(facts)})**")
                if not facts: 
                    st.warning("Факты не найдены.")
                for f in facts: 
                    st.markdown(f"- **[{f.get('category','').upper()}]** {f.get('claim','')} {get_score_badge(f.get('similarity', 0))}", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(f"**🔗 Страницы для перелинковки ({len(pages)})**")
                if not pages: 
                    st.info("Страницы еще не загружены в базу.")
                for p in pages: 
                    st.markdown(f"- [{p.get('title','')}]({p.get('url','')}) {get_score_badge(p.get('similarity', 0))}", unsafe_allow_html=True)

        if facts:
            with c_right:
                with st.container(border=True):
                    st.markdown("#### ✨ Результат генерации")
                    with st.spinner("Генерация текста с внедрением ссылок..."):
                        facts_context = "\n".join([f"- [{f.get('category','')}] {f.get('claim','')}" for f in facts])
                        links_context = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages]) if pages else "Внутренние ссылки отсутствуют"
                        gen_prompt = f"Ты — SEO-копирайтер для {selected_product}.\nНапиши {content_type} под запрос '{target_kw}'.\nПравила:\n1. ТОЛЬКО факты из базы.\n2. Вставь 2-3 ссылки.\nФАКТЫ:\n{facts_context}\nСТРАНИЦЫ:\n{links_context}"
                        generated_text = generate_llm(gen_prompt, temperature=0.2)
                        st.markdown(generated_text)
                with st.container(border=True):
                    st.markdown("#### 🩺 Аудит агентом «Доктор»")
                    with st.spinner("Проверка..."):
                        doc_prompt = f"Проверь текст на соответствие фактам:\nФАКТЫ:\n{facts_context}\nТЕКСТ:\n{generated_text}\nВердикт: Есть галлюцинации? Статус: PASS или FAIL."
                        doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                        
                        if "PASS" in doc_verdict.upper(): 
                            st.success(doc_verdict)
                        else: 
                            st.error(doc_verdict)
                            
                        save_generation_to_history(selected_product, st.session_state["username"], target_kw, content_type, generated_text, doc_verdict)

# 2. GAP AUDIT
elif st.session_state.active_tab.startswith("📊 Gap"):
    with st.container(border=True):
        st.markdown("#### Параметры аудита")
        default_audit = f"How {selected_product} pricing and Shopify limits work?" if selected_product == "toriut" else f"Can {selected_product} integrate with HubSpot?"
        audit_kw = st.text_input("Проверить поисковый запрос на слепые зоны", value=default_audit)
        run_audit = st.button("🔍 Провести аудит", type="primary")

    if run_audit:
        with st.spinner("Анализ векторной базы и структуры сайта..."):
            audit_facts = retrieve_facts(audit_kw, selected_product, top_k=3, threshold=0.0)
            pages_to_update = retrieve_linking_pages(audit_kw, selected_product, top_k=4)
            
            if audit_facts:
                best_sc = audit_facts[0].get("similarity", 0)
                if best_sc > 0.65: 
                    st.markdown(f"<div style='background-color:#1E3E23; padding:15px; border-radius:8px; border-left: 5px solid #68D391; color: #E2E8F0;'><b>🟢 Отличное покрытие базы знаний!</b> Максимальная близость: {best_sc:.2f}</div><br>", unsafe_allow_html=True)
                elif best_sc > 0.45: 
                    st.markdown(f"<div style='background-color:#4A3500; padding:15px; border-radius:8px; border-left: 5px solid #F6AD55; color: #E2E8F0;'><b>🟡 Среднее покрытие.</b> Факты найдены, но могут быть слишком общими (Близость: {best_sc:.2f}).</div><br>", unsafe_allow_html=True)
                else: 
                    st.markdown(f"<div style='background-color:#4A1C1A; padding:15px; border-radius:8px; border-left: 5px solid #FC8181; color: #E2E8F0;'><b>🔴 Слепая зона.</b> Прямых фактов нет (Близость: {best_sc:.2f}). Требуется актуализация.</div><br>", unsafe_allow_html=True)

                c1, c2 = st.columns([1, 1.2])
                with c1:
                    with st.container(border=True):
                        st.markdown("**Найденные факты в базе:**")
                        facts_text = ""
                        for af in audit_facts:
                            st.markdown(f"- {af.get('claim','')} {get_score_badge(af.get('similarity',0))}", unsafe_allow_html=True)
                            facts_text += f"- {af.get('claim','')}\n"
                with c2:
                    with st.container(border=True):
                        st.markdown("**Ближайшие страницы сайта (Кандидаты на обновление):**")
                        pages_text = ""
                        if pages_to_update:
                            for pu in pages_to_update:
                                st.markdown(f"- [{pu.get('title', 'Без названия')}]({pu.get('url', '')}) {get_score_badge(pu.get('similarity',0))}", unsafe_allow_html=True)
                                pages_text += f"- [{pu.get('title', 'Без названия')}]({pu.get('url', '')})\n"
                        else: 
                            st.info("Подходящих страниц не найдено.")

                with st.container(border=True):
                    st.markdown("#### 🕵️ Пруфы аудита (Анализ от AI-стратега)")
                    with st.spinner("LLM анализирует нехватку данных..."):
                        proof_prompt = f"""Ты — Lead Content Strategist для {selected_product}.
SEO-специалист проверяет интент: '{audit_kw}'.
Найдены фрагменты в базе:
{facts_text}
Релевантные страницы сайта:
{pages_text}

Проведи глубокий аудит и дай расширенные советы (форматируй красиво через Markdown, используй списки):
1. 🎯 Вердикт по интенту: Насколько текущая база фактов закрывает боль пользователя? Хватит ли этого для экспертной статьи или получится рерайт/вода?
2. 🚨 Слепые зоны (Missing Info): Чего критически не хватает в нашей базе, чтобы стать ответом №1 в Google? Какие конкретно детали/фичи нужно срочно вытянуть из продакт-менеджера?
3. 🛠 Actionable Advice (Как и где исправить): Выбери 1-2 страницы из списка и дай развернутые советы по их улучшению. Что конкретно туда дописать? Какие новые H2/H3 блоки или таблицы добавить, чтобы закрыть интент? Обязательно сохрани ссылки на эти страницы в ответе."""
                        
                        audit_proof = generate_llm(proof_prompt, temperature=0.3)
                        st.info(audit_proof)
                        
                        audit_status = "PASS" if best_sc >= 0.45 else "FAIL"
                        save_generation_to_history(
                            product=selected_product, 
                            author=st.session_state["username"], 
                            kw=audit_kw, 
                            content_type="Gap Audit", 
                            text=audit_proof, 
                            verdict=f"Max Similarity: {best_sc:.2f} (Status: {audit_status})"
                        )
            else: 
                st.error("Факты не найдены в базе вообще. Это абсолютная слепая зона.")

# 3. DATA MANAGER
elif st.session_state.active_tab.startswith("⚙️ Data"):
    col_maps, col_playbooks = st.columns([1, 1])
    with col_maps:
        with st.container(border=True):
            st.markdown("#### 🌐 Мониторинг Sitemap")
            st.caption("Парсинг сайтмапов для отслеживания новых лендингов и обновления старых страниц.")
            st.markdown("<p style='font-size:0.9em; opacity:0.8;'><b>💡 Быстрый парсинг:</b></p>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            btn_pics = c1.button("🚀 pics.io", use_container_width=True)
            btn_bpics = c1.button("🚀 blog.pics.io", use_container_width=True)
            btn_toriut = c2.button("🚀 toriut.com", use_container_width=True)
            btn_btoriut = c2.button("🚀 blog.toriut.com", use_container_width=True)
            
            target_sitemap = st.text_input("Или введите вручную URL Sitemap:", value="https://pics.io/sitemap.xml")
            btn_manual = st.button("🔍 Спарсить введенный", type="primary", use_container_width=True)
            
            active_sitemap = None
            if btn_pics: active_sitemap = "https://pics.io/sitemap.xml"
            elif btn_bpics: active_sitemap = "https://blog.pics.io/sitemap.xml"
            elif btn_toriut: active_sitemap = "https://toriut.com/sitemap.xml"
            elif btn_btoriut: active_sitemap = "https://blog.toriut.com/sitemap.xml"
            elif btn_manual and target_sitemap: active_sitemap = target_sitemap.strip()
            
            if active_sitemap:
                with st.spinner(f"Чтение {active_sitemap}..."):
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        r = requests.get(active_sitemap, headers=headers, timeout=20)
                        r.raise_for_status()
                        root = ET.fromstring(r.content)
                        for elem in root.iter():
                            if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
                        results = []
                        if root.tag == 'sitemapindex':
                            for s in root.findall('sitemap'): 
                                results.append({"Тип": "Индекс", "URL": s.findtext('loc', '-'), "Обновлено": s.findtext('lastmod', '-')})
                        elif root.tag == 'urlset':
                            for u in root.findall('url'): 
                                results.append({"Тип": "Страница", "URL": u.findtext('loc', '-'), "Обновлено": u.findtext('lastmod', '-')})
                        if results:
                            st.dataframe(pd.DataFrame(results).sort_values(by="Обновлено", ascending=False), use_container_width=True, hide_index=True)
                        else: 
                            st.warning("Ссылок не найдено.")
                    except Exception as e: 
                        st.error(f"Ошибка: {e}")

    with col_playbooks:
        with st.container(border=True):
            st.markdown("#### 🚀 Плейбуки новых лендингов")
            new_url = st.text_input("URL новой страницы", placeholder="https://pics.io/new-feature")
            new_keywords = st.text_input("Главные ключевые слова", placeholder="AI search")
            playbook_text = st.text_area("Текст плейбука", height=120)
            uploaded_playbook = st.file_uploader("Или файл (.txt, .md)", type=["txt", "md"])
            
            if st.button("🧠 Найти места для размещения", type="primary", use_container_width=True):
                final_text = playbook_text.strip()
                if uploaded_playbook: 
                    final_text += "\n\n" + uploaded_playbook.read().decode("utf-8")
                if final_text.strip():
                    with st.spinner("Анализ базы..."):
                        candidates = retrieve_linking_pages(final_text.strip(), selected_product, top_k=3)
                        if candidates:
                            for c in candidates:
                                with st.container(border=True):
                                    st.markdown(f"**🔗 [{c.get('title', 'URL')}]({c.get('url', '')})** {get_score_badge(c.get('similarity', 0))}", unsafe_allow_html=True)
                                    target_link = new_url.strip() if new_url.strip() else "[URL_БУДЕТ_ЗДЕСЬ]"
                                    st.info(generate_llm(f"SEO-стратег для {selected_product}. Мы готовим новую страницу:\n{new_keywords}\nБриф:\n{final_text}\nНапиши 1-2 предложения для добавления на старую страницу ({c.get('url', '')}). Ссылка: [Анкор]({target_link}).", temperature=0.3))
                        else: 
                            st.warning("Страниц не найдено.")
                else: 
                    st.error("Добавьте текст.")

# 4. ЛИНК-БИЛДЕР
elif st.session_state.active_tab.startswith("🔗 Линк"):
    with st.container(border=True):
        st.markdown("#### 🔗 Векторный подбор страниц сайта")
        search_link_kw = st.text_input("Тема для подбора URL", value="Digital Asset Management")
        if st.button("Найти URL", type="primary"):
            found_pages = retrieve_linking_pages(search_link_kw, selected_product, top_k=8)
            if not found_pages: 
                st.info("Страницы не загружены.")
            for fp in found_pages:
                with st.container(border=True):
                    st.markdown(f"**[{fp.get('title','')}]({fp.get('url','')})** {get_score_badge(fp.get('similarity',0))}", unsafe_allow_html=True)

# 5. BATCH
elif st.session_state.active_tab.startswith("⚡ Batch"):
    with st.container(border=True):
        st.markdown("#### ⚡ Пакетная генерация")
        batch_input = st.text_area("Ключи (по одному на строку)", value="Google Drive DAM integration")
        batch_type = st.selectbox("Формат", ["Meta Title + Description", "SEO Article Section"])
        if st.button("🚀 Запустить", type="primary"):
            keywords = [k.strip() for k in batch_input.split("\n") if k.strip()]
            results = []
            bar = st.progress(0)
            for i, kw in enumerate(keywords):
                facts = retrieve_facts(kw, selected_product, top_k=4)
                facts_context = "\n".join([f"- {f.get('claim','')}" for f in facts])
                
                txt = generate_llm(f"Напиши {batch_type} для {selected_product} по теме '{kw}'. Факты:\n{facts_context}")
                
                doc_prompt = f"Проверь текст на соответствие фактам:\nФАКТЫ:\n{facts_context}\nТЕКСТ:\n{txt}\nВердикт: Есть галлюцинации? Статус: PASS или FAIL."
                doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                
                save_generation_to_history(selected_product, st.session_state["username"], kw, batch_type, txt, doc_verdict)
                
                status_badge = "✅ PASS" if "PASS" in doc_verdict.upper() else "❌ FAIL"
                results.append({"Ключ": kw, "Текст": txt, "Статус": status_badge})
                bar.progress((i + 1) / len(keywords))
                
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)
            st.success("🎉 Пакетная генерация завершена! Все результаты сохранены в Историю.")

# 6. ИСТОРИЯ
elif st.session_state.active_tab.startswith("📜 История"):
    with st.container(border=True):
        hist_data = get_content_history(selected_product)
        if hist_data:
            df_hist = pd.DataFrame(hist_data)
            st.dataframe(df_hist[["created_at", "target_keyword", "status"]], hide_index=True, use_container_width=True)
            selected_id = st.selectbox("Открыть лог:", df_hist["id"].tolist())
            row = next(r for r in hist_data if r["id"] == selected_id)
            st.markdown(row["generated_text"])
            st.info(row.get('doctor_verdict',''))
        else: 
            st.info(f"История для {selected_product.upper()} пока пуста.")
