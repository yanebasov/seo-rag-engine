import os
import json
import re
import xml.etree.ElementTree as ET
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

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

if "edit_link_id" not in st.session_state:
    st.session_state.edit_link_id = None

# --- CUSTOM CSS ---
st.markdown("""
<style>
    [data-testid="stSidebar"] .stButton > button {
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
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
    .badge-green { background-color: rgba(46, 133, 64, 0.2); color: #2E7D32; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(46, 133, 64, 0.4); }
    .badge-yellow { background-color: rgba(245, 158, 11, 0.2); color: #D97706; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-red { background-color: rgba(239, 68, 68, 0.2); color: #DC2626; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-neutral { background-color: rgba(128, 128, 128, 0.15); color: var(--text-color); padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 8px; }
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

def shorten_url(url, max_len=30):
    if not url or str(url) == "#" or str(url).lower() == "none": return "—"
    clean = str(url).replace("https://", "").replace("http://", "").replace("www.", "")
    if len(clean) > max_len: return clean[:max_len] + "..."
    return clean

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
            if st.session_state.selected_product == "pics.io": st.image("picsio_logo.jpeg", use_container_width=True)
            else: st.image("toriut_logo.jpeg", use_container_width=True)
        except Exception: pass
            
    st.write("") 
    selected_product = st.selectbox(
        "Продукт", options=["pics.io", "toriut"],
        format_func=lambda x: "Pics.io (DAM)" if x == "pics.io" else "Toriut (PIM)",
        key="selected_product", label_visibility="collapsed"
    )
    st.divider()

    st.markdown(f"👤 **Пользователь:** <span class='badge-neutral'>{st.session_state['username']}</span>", unsafe_allow_html=True)
    if st.button("🚪 Выйти", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    
    st.write("")
    st.markdown("<p style='opacity: 0.7; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:10px;'>MODULES</p>", unsafe_allow_html=True)
    
    menu_items = ["✍️ Генерация + Доктор", "📊 Gap Audit", "🌐 Link Checker", "⚙️ Data Manager", "🔗 Линк-билдер", "⚡ Batch Processing", "📜 История"]
    
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = menu_items[0]
        
    for item in menu_items:
        btn_type = "primary" if st.session_state.active_tab == item else "secondary"
        if st.button(item, key=f"nav_{item}", use_container_width=True, type=btn_type):
            st.session_state.active_tab = item
            st.session_state.edit_link_id = None
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
            embed_m = next((c for c in embed_cands if "text-embedding-004" in c), embed_cands[0] if embed_cands else None)
            gen_m = next((c for c in gen_cands if "gemini-1.5-flash" in c), gen_cands[0] if gen_cands else None)
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
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

def get_embedding(text: str):
    if not CURRENT_KEY or not EMBED_MODEL: return None
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent?key={CURRENT_KEY}", json={"content": {"parts": [{"text": text}]}}, timeout=10)
        if res.status_code == 200: return res.json()["embedding"]["values"][:768]
    except: pass
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_KEY or not GEN_MODEL: return "Ошибка: API Key."
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/{GEN_MODEL}:generateContent?key={CURRENT_KEY}", json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}, timeout=30)
        if res.status_code == 200: return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"⚠️ Ошибка ({res.status_code}): {res.json().get('error', {}).get('message', '')}"
    except Exception as e: return f"⚠️ Ошибка: {e}"

def retrieve_facts(query: str, product: str, top_k: int = 6, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: return []
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/match_toriut_facts" if product == "toriut" else f"{SUPABASE_URL}/rest/v1/rpc/match_facts"
    payload = {"query_embedding": vec, "match_threshold": threshold, "match_count": top_k}
    if product != "toriut": payload["filter_product"] = product
    try:
        res = requests.post(rpc_url, headers=get_supabase_headers(), json=payload, timeout=10)
        if res.status_code == 200: return res.json()
    except: pass
    return []

def retrieve_linking_pages(query: str, product: str, top_k: int = 4, threshold: float = 0.0):
    vec = get_embedding(query)
    if not vec: return []
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/match_site_pages", headers=get_supabase_headers(), json={"query_embedding": vec, "match_threshold": threshold, "match_count": top_k, "filter_product": product}, timeout=10)
        if res.status_code == 200: return res.json()
    except: pass
    return []

def save_generation_to_history(product, author, kw, content_type, text, verdict):
    payload = {"product": product, "author": author, "target_keyword": kw, "content_type": content_type, "generated_text": text, "doctor_verdict": verdict, "status": "PASS" if "PASS" in str(verdict).upper() else "FAIL"}
    try: requests.post(f"{SUPABASE_URL}/rest/v1/content_history", headers=get_supabase_headers(), json=payload, timeout=10)
    except: pass

def get_content_history(product: str):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/content_history?product=eq.{product}&order=created_at.desc&limit=20", headers=get_supabase_headers(), timeout=8)
        if res.status_code == 200: return res.json()
    except: pass
    return []

def check_link_status(page_url, target_url, target_keyword):
    """
    Универсальная функция парсинга. Защищена от None.
    """
    status_code = 0
    attr_result = "Not Found"
    
    safe_t_url = str(target_url).lower().strip() if target_url else ""
    safe_t_kw = str(target_keyword).lower().strip() if target_keyword else ""
    
    t_url_lower = safe_t_url if safe_t_url not in ["none", "#", "—", ""] else ""
    t_kw_lower = safe_t_kw if safe_t_kw not in ["none", "#", "—", ""] else ""
    
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(page_url, headers=headers, timeout=10)
        status_code = resp.status_code
        
        if status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            found_url = False
            found_exact = False
            
            for a in soup.find_all('a', href=True):
                href_val = a['href'].lower()
                txt_val = a.get_text().strip().lower()
                
                url_match = (t_url_lower in href_val) if t_url_lower else True
                kw_match = (t_kw_lower in txt_val or t_kw_lower in href_val) if t_kw_lower else True
                
                if url_match:
                    found_url = True
                    if kw_match:
                        found_exact = True
                        rel_vals = [r.lower() for r in a.get('rel', [])]
                        attr_result = "nofollow" if 'nofollow' in rel_vals else "dofollow"
                        break
            
            if not found_url: attr_result = "Link Missing"
            elif found_url and not found_exact: attr_result = "Wrong Anchor"
        else:
            attr_result = f"HTTP Error {status_code}"
    except Exception:
        status_code = 0
        attr_result = "Error"
        
    return status_code, attr_result

# --- MAIN CONTENT AREA ---
st.title(st.session_state.active_tab.split(" (")[0])

# 1. ГЕНЕРАЦИЯ + ДОКТОР
if st.session_state.active_tab.startswith("✍️ Генерация"):
    with st.container(border=True):
        col1, col2 = st.columns([1, 1])
        default_kw = "Toriut Shopify integration features" if selected_product == "toriut" else "Google Drive DAM integration features"
        with col1: target_kw = st.text_input("Целевой ключевой запрос", value=default_kw)
        with col2: content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        c1, c2 = st.columns(2)
        with c1: top_k = st.slider("Количество фактов из базы", 2, 12, 6)
        with c2: top_links_count = st.slider("Количество внутренних ссылок", 1, 6, 3)
        run_btn = st.button("🚀 Сгенерировать контент", type="primary", use_container_width=True)

    if run_btn and target_kw:
        st.divider()
        with st.spinner("Сбор данных..."):
            facts = retrieve_facts(target_kw, selected_product, top_k=top_k)
            pages = retrieve_linking_pages(target_kw, selected_product, top_k=top_links_count)
            
        c_left, c_right = st.columns([1.2, 2])
        with c_left:
            with st.container(border=True):
                st.markdown(f"**📚 Факты ({len(facts)})**")
                for f in facts: st.markdown(f"- **[{f.get('category','').upper()}]** {f.get('claim','')} {get_score_badge(f.get('similarity', 0))}", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(f"**🔗 Перелинковка ({len(pages)})**")
                for p in pages: st.markdown(f"- [{p.get('title','')}]({p.get('url','')}) {get_score_badge(p.get('similarity', 0))}", unsafe_allow_html=True)

        if facts:
            with c_right:
                with st.container(border=True):
                    st.markdown("#### ✨ Результат генерации")
                    facts_context = "\n".join([f"- [{f.get('category','')}] {f.get('claim','')}" for f in facts])
                    links_context = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in pages]) if pages else "Внутренние ссылки отсутствуют"
                    gen_prompt = f"Ты — SEO-копирайтер для {selected_product}.\nНапиши {content_type} под запрос '{target_kw}'.\nПравила:\n1. ТОЛЬКО факты из базы.\n2. Вставь 2-3 ссылки.\nФАКТЫ:\n{facts_context}\nСТРАНИЦЫ:\n{links_context}"
                    generated_text = generate_llm(gen_prompt, temperature=0.2)
                    st.markdown(generated_text)
                with st.container(border=True):
                    st.markdown("#### 🩺 Аудит агентом «Доктор»")
                    doc_prompt = f"Проверь текст на соответствие фактам:\nФАКТЫ:\n{facts_context}\nТЕКСТ:\n{generated_text}\nВердикт: Есть галлюцинации? Статус: PASS или FAIL."
                    doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                    if "PASS" in doc_verdict.upper(): st.success(doc_verdict)
                    else: st.error(doc_verdict)
                    save_generation_to_history(selected_product, st.session_state["username"], target_kw, content_type, generated_text, doc_verdict)

# 2. GAP AUDIT
elif st.session_state.active_tab.startswith("📊 Gap"):
    with st.container(border=True):
        default_audit = f"How {selected_product} pricing and Shopify limits work?" if selected_product == "toriut" else f"Can {selected_product} integrate with HubSpot?"
        audit_kw = st.text_input("Проверить поисковый запрос на слепые зоны", value=default_audit)
        run_audit = st.button("🔍 Провести аудит", type="primary")

    if run_audit:
        with st.spinner("Анализ..."):
            audit_facts = retrieve_facts(audit_kw, selected_product, top_k=3, threshold=0.0)
            pages_to_update = retrieve_linking_pages(audit_kw, selected_product, top_k=4)
            if audit_facts:
                best_sc = audit_facts[0].get("similarity", 0)
                if best_sc > 0.65: st.markdown(f"<div style='background-color:#1E3E23; padding:15px; border-radius:8px; border-left: 5px solid #68D391; color: #E2E8F0;'><b>🟢 Отличное покрытие базы знаний!</b> Близость: {best_sc:.2f}</div><br>", unsafe_allow_html=True)
                elif best_sc > 0.45: st.markdown(f"<div style='background-color:#4A3500; padding:15px; border-radius:8px; border-left: 5px solid #F6AD55; color: #E2E8F0;'><b>🟡 Среднее покрытие.</b> Близость: {best_sc:.2f}</div><br>", unsafe_allow_html=True)
                else: st.markdown(f"<div style='background-color:#4A1C1A; padding:15px; border-radius:8px; border-left: 5px solid #FC8181; color: #E2E8F0;'><b>🔴 Слепая зона.</b> Близость: {best_sc:.2f}</div><br>", unsafe_allow_html=True)

                facts_text = "".join([f"- {af.get('claim','')}\n" for af in audit_facts])
                pages_text = "".join([f"- [{pu.get('title', 'Без названия')}]({pu.get('url', '')})\n" for pu in pages_to_update])

                with st.container(border=True):
                    st.markdown("#### 🕵️ Пруфы аудита (Анализ от AI-стратега)")
                    proof_prompt = f"Ты Lead Content Strategist для {selected_product}.\nSEO-специалист проверяет интент: '{audit_kw}'.\nНайдены фрагменты:\n{facts_text}\nРелевантные страницы:\n{pages_text}\nДай советы:\n1. Вердикт по интенту\n2. Слепые зоны\n3. Actionable Advice."
                    audit_proof = generate_llm(proof_prompt, temperature=0.3)
                    st.info(audit_proof)
                    save_generation_to_history(selected_product, st.session_state["username"], audit_kw, "Gap Audit", audit_proof, f"Max Similarity: {best_sc:.2f}")

# 2.1. LINK CHECKER (Мониторинг бэклинков)
elif st.session_state.active_tab.startswith("🌐 Link Checker"):
    with st.container(border=True):
        st.markdown(f"#### 🌐 Мониторинг бэклинков ({selected_product.upper()})")
        
        tab_single, tab_batch = st.tabs(["➕ Добавить одну ссылку", "📁 Загрузить файлом (CSV / TXT)"])
        
        single_to_add = None
        batch_items = []
        
        with tab_single:
            col_s1, col_s2, col_s3 = st.columns([1.5, 1.5, 1])
            with col_s1: single_url = st.text_input("URL статьи (где размещен бэклинк)", key="single_url_inp")
            with col_s2: single_target = st.text_input("Куда ссылаемся (Target URL)", key="single_target_inp")
            with col_s3: single_kw = st.text_input("Ключевое слово / Бренд", key="single_kw_inp")
            if st.button("Проверить и сохранить", type="primary"):
                if single_url.strip() and single_target.strip() and single_kw.strip(): single_to_add = (single_url.strip(), single_target.strip(), single_kw.strip())
                else: st.warning("Заполните все три поля: URL статьи, Target URL и Ключ.")

        with tab_batch:
            st.caption("Формат CSV: `URL статьи, Target URL, Ключ`. В TXT: строка вида `URL статьи | Target URL | Ключ`")
            uploaded_links_file = st.file_uploader("Выберите файл", type=["csv", "txt"])
            if st.button("🚀 Запустить массовую проверку", type="primary"):
                if uploaded_links_file:
                    content = uploaded_links_file.read().decode("utf-8")
                    for line in content.splitlines():
                        sep = "|" if "|" in line else ","
                        parts = line.split(sep)
                        if len(parts) >= 3:
                            u, targ, k = [p.strip().strip('"').strip("'") for p in parts[:3]]
                            if u.startswith("http"): batch_items.append((u, targ, k))
                else: st.warning("Загрузите файл.")

        queue_to_process = []
        if single_to_add: queue_to_process.append(single_to_add)
        if batch_items: queue_to_process.extend(batch_items)

        if queue_to_process:
            bar = st.progress(0)
            success_cnt = 0
            for idx, (url_to_check, target_url, target_brand) in enumerate(queue_to_process):
                status_code, attr_result = check_link_status(url_to_check, target_url, target_brand)
                
                payload = {
                    "product": selected_product, 
                    "page_url": url_to_check, 
                    "target_url": target_url, 
                    "target_keyword": target_brand, 
                    "http_status": status_code, 
                    "link_attribute": attr_result
                }
                try:
                    requests.post(f"{SUPABASE_URL}/rest/v1/link_checker", headers=get_supabase_headers(), json=payload, timeout=5)
                    success_cnt += 1
                except: pass
                bar.progress((idx + 1) / len(queue_to_process))
            st.success(f"Готово! Проверено и сохранено: {success_cnt}")
            st.rerun()

        st.divider()
        
        if st.button("🔄 Перепроверить всю базу ссылок (Авто-парсинг)", type="primary"):
            try:
                r_all = requests.get(f"{SUPABASE_URL}/rest/v1/link_checker?product=eq.{selected_product}", headers=get_supabase_headers(), timeout=10)
                if r_all.status_code == 200:
                    all_links = r_all.json()
                    bar = st.progress(0)
                    for i, lnk in enumerate(all_links):
                        r_id = lnk["id"]
                        s_code, a_res = check_link_status(lnk.get("page_url",""), lnk.get("target_url",""), lnk.get("target_keyword",""))
                        requests.patch(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{r_id}", headers=get_supabase_headers(), json={"http_status": s_code, "link_attribute": a_res}, timeout=5)
                        bar.progress((i+1) / len(all_links))
                    st.success("Все ссылки успешно перепроверены!")
            except Exception as e:
                st.error(f"Ошибка перепроверки: {e}")

        st.write("")
        
        try:
            get_links_url = f"{SUPABASE_URL}/rest/v1/link_checker?product=eq.{selected_product}&order=checked_at.desc"
            r_links = requests.get(get_links_url, headers=get_supabase_headers(), timeout=10)
            
            if r_links.status_code == 200:
                links_data = r_links.json()
                if links_data:
                    items_per_page = 10
                    total_items = len(links_data)
                    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
                    
                    if "link_checker_page" not in st.session_state: st.session_state.link_checker_page = 1
                    if st.session_state.link_checker_page > total_pages: st.session_state.link_checker_page = total_pages

                    start_idx = (st.session_state.link_checker_page - 1) * items_per_page
                    end_idx = start_idx + items_per_page
                    page_data = links_data[start_idx:end_idx]
                    
                    st.caption(f"Показано с {start_idx + 1} по {min(total_items, end_idx)} из {total_items} бэклинков")

                    # Шапка таблицы
                    head_cols = st.columns([1.9, 1.9, 1.2, 0.7, 0.9, 0.9, 0.9, 1.3])
                    head_cols[0].markdown("**Статья**")
                    head_cols[1].markdown("**Цель**")
                    head_cols[2].markdown("**Ключ**")
                    head_cols[3].markdown("**Статус**")
                    head_cols[4].markdown("**HTTP**")
                    head_cols[5].markdown("**Атрибут**")
                    head_cols[6].markdown("**Проверено**")
                    head_cols[7].markdown("**Действия**")
                    st.divider()

                    for row in page_data:
                        try:
                            row_id = row.get("id")
                            
                            raw_checked = row.get("checked_at")
                            checked_time = str(raw_checked).replace("T", " ")[:16] if raw_checked else "—"
                            
                            p_url = str(row.get("page_url") or "#")
                            
                            raw_t_url = row.get("target_url")
                            t_url = str(raw_t_url) if raw_t_url else "#"
                            if t_url.lower() == "none" or not t_url.strip(): t_url = "#"
                                
                            raw_kw = row.get("target_keyword")
                            t_kw = str(raw_kw) if raw_kw else "—"
                            if t_kw.lower() == "none" or not t_kw.strip(): t_kw = "—"
                                
                            if st.session_state.edit_link_id == row_id:
                                # РЕЖИМ РЕДАКТИРОВАНИЯ
                                with st.container(border=True):
                                    col_e1, col_e2, col_e3 = st.columns(3)
                                    new_p_url = col_e1.text_input("URL статьи", value=p_url, key=f"ep_{row_id}")
                                    new_t_url = col_e2.text_input("Target URL", value="" if t_url == "#" else t_url, key=f"et_{row_id}")
                                    new_kw = col_e3.text_input("Ключ", value="" if t_kw == "—" else t_kw, key=f"ek_{row_id}")
                                    
                                    ce_1, ce_2, _ = st.columns([1.5, 1.5, 5])
                                    if ce_1.button("💾 Сохранить и парсить", key=f"save_{row_id}", type="primary"):
                                        s_code, a_res = check_link_status(new_p_url, new_t_url, new_kw)
                                        payload = {"page_url": new_p_url, "target_url": new_t_url, "target_keyword": new_kw, "http_status": s_code, "link_attribute": a_res}
                                        try:
                                            requests.patch(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{row_id}", headers=get_supabase_headers(), json=payload, timeout=5)
                                            st.toast("Ссылка обновлена!")
                                        except Exception as db_err:
                                            st.error(f"Сбой БД: {db_err}")
                                        st.session_state.edit_link_id = None
                                        st.rerun()
                                    if ce_2.button("❌ Отмена", key=f"cancel_{row_id}"):
                                        st.session_state.edit_link_id = None
                                        st.rerun()
                            else:
                                # РЕЖИМ ПРОСМОТРА
                                h_status = row.get("http_status", 0)
                                l_attr = str(row.get("link_attribute") or "Unknown")
                                
                                if h_status == 200 and l_attr in ["dofollow", "nofollow"]: live_badge = "<span class='badge-green'>🟢 Live</span>"
                                else: live_badge = "<span class='badge-red'>🔴 Dead</span>"

                                status_badge = f"<span class='badge-green'>HTTP {h_status}</span>" if h_status == 200 else f"<span class='badge-red'>HTTP {h_status}</span>"
                                attr_badge = f"<span class='badge-green'>{l_attr}</span>" if l_attr == "dofollow" else (f"<span class='badge-yellow'>{l_attr}</span>" if l_attr == "nofollow" else f"<span class='badge-red'>{l_attr}</span>")

                                short_p = shorten_url(p_url, 30)
                                short_t = shorten_url(t_url, 30)

                                with st.container(border=True):
                                    c_u, c_tar, c_k, c_l, c_s, c_a, c_t, c_act = st.columns([1.9, 1.9, 1.2, 0.7, 0.9, 0.9, 0.9, 1.3])
                                    c_u.markdown(f"[{short_p}]({p_url})", unsafe_allow_html=True)
                                    c_tar.markdown(f"[{short_t}]({t_url})", unsafe_allow_html=True)
                                    c_k.markdown(f"`{t_kw}`")
                                    c_l.markdown(live_badge, unsafe_allow_html=True)
                                    c_s.markdown(status_badge, unsafe_allow_html=True)
                                    c_a.markdown(attr_badge, unsafe_allow_html=True)
                                    c_t.markdown(f"<span style='opacity:0.6; font-size:0.8em;'>{checked_time}</span>", unsafe_allow_html=True)
                                    
                                    ca1, ca2, ca3 = c_act.columns([1, 1, 1])
                                    if ca1.button("🔄", key=f"ref_{row_id}", help="Перепроверить статус сейчас"):
                                        ns_code, na_res = check_link_status(p_url, t_url, t_kw)
                                        requests.patch(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{row_id}", headers=get_supabase_headers(), json={"http_status": ns_code, "link_attribute": na_res}, timeout=5)
                                        st.rerun()
                                    if ca2.button("✏️", key=f"edit_btn_{row_id}", help="Редактировать"):
                                        st.session_state.edit_link_id = row_id
                                        st.rerun()
                                    if ca3.button("🗑️", key=f"del_link_{row_id}", help="Удалить из базы"):
                                        requests.delete(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{row_id}", headers=get_supabase_headers(), timeout=5)
                                        st.rerun()
                        except Exception as row_err:
                            st.error(f"Сбой при отображении ссылки. Запись пропущена.")

                    if total_pages > 1:
                        st.write("")
                        cols_pag = st.columns(min(15, total_pages) + 2)
                        for p_num in range(1, total_pages + 1):
                            if cols_pag[p_num - 1].button(str(p_num), key=f"pag_btn_{p_num}", type="primary" if p_num == st.session_state.link_checker_page else "secondary"):
                                st.session_state.link_checker_page = p_num
                                st.rerun()

                    st.write("")
                    st.download_button("📥 Экспорт в CSV", data=pd.DataFrame(links_data).to_csv(index=False).encode('utf-8'), file_name=f"link_checker_{selected_product}.csv", mime="text/csv", type="primary")
                else:
                    st.info(f"Список бэклинков для {selected_product.upper()} пока пуст.")
            else:
                st.error(f"Ошибка загрузки базы. Код сервера: {r_links.status_code}")
        except Exception as e:
            st.error(f"Сервер БД временно недоступен: {e}")

# 3. DATA MANAGER
elif st.session_state.active_tab.startswith("⚙️ Data"):
    col_maps, col_playbooks = st.columns([1, 1])
    with col_maps:
        with st.container(border=True):
            st.markdown("#### 🌐 Мониторинг Sitemap")
            c1, c2 = st.columns(2)
            btn_pics = c1.button("🚀 pics.io", use_container_width=True)
            btn_bpics = c1.button("🚀 blog.pics.io", use_container_width=True)
            btn_toriut = c2.button("🚀 toriut.com", use_container_width=True)
            btn_btoriut = c2.button("🚀 blog.toriut.com", use_container_width=True)
            target_sitemap = st.text_input("Или введите вручную URL Sitemap:", value="https://pics.io/sitemap.xml")
            btn_manual = st.button("🔍 Спарсить", type="primary", use_container_width=True)
            
            active_sitemap = None
            if btn_pics: active_sitemap = "https://pics.io/sitemap.xml"
            elif btn_bpics: active_sitemap = "https://blog.pics.io/sitemap.xml"
            elif btn_toriut: active_sitemap = "https://toriut.com/sitemap.xml"
            elif btn_btoriut: active_sitemap = "https://blog.toriut.com/sitemap.xml"
            elif btn_manual and target_sitemap: active_sitemap = target_sitemap.strip()
            
            if active_sitemap:
                with st.spinner(f"Чтение {active_sitemap}..."):
                    try:
                        r = requests.get(active_sitemap, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
                        if r.status_code == 200:
                            root = ET.fromstring(r.content)
                            for elem in root.iter():
                                if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
                            res = []
                            if root.tag == 'sitemapindex':
                                for s in root.findall('sitemap'): res.append({"Тип": "Индекс", "URL": s.findtext('loc', '-'), "Обновлено": s.findtext('lastmod', '-')})
                            elif root.tag == 'urlset':
                                for u in root.findall('url'): res.append({"Тип": "Страница", "URL": u.findtext('loc', '-'), "Обновлено": u.findtext('lastmod', '-')})
                            st.dataframe(pd.DataFrame(res).sort_values(by="Обновлено", ascending=False), use_container_width=True, hide_index=True)
                    except: pass

    with col_playbooks:
        with st.container(border=True):
            st.markdown("#### 🚀 Плейбуки")
            new_url = st.text_input("URL новой страницы")
            new_keywords = st.text_input("Главные ключи")
            playbook_text = st.text_area("Текст плейбука", height=120)
            if st.button("🧠 Найти места для размещения", type="primary", use_container_width=True):
                if playbook_text.strip():
                    with st.spinner("Анализ..."):
                        candidates = retrieve_linking_pages(playbook_text.strip(), selected_product, top_k=3)
                        for c in candidates:
                            with st.container(border=True):
                                st.markdown(f"**🔗 [{c.get('title', 'URL')}]({c.get('url', '')})** {get_score_badge(c.get('similarity', 0))}", unsafe_allow_html=True)
                                st.info(generate_llm(f"SEO-стратег для {selected_product}.\nБриф:\n{playbook_text}\nНапиши 1-2 предложения для вставки на страницу ({c.get('url', '')}). Ссылка: {new_url}.", temperature=0.3))

# 4. ЛИНК-БИЛДЕР
elif st.session_state.active_tab.startswith("🔗 Линк"):
    with st.container(border=True):
        st.markdown("#### 🔗 Векторный подбор страниц")
        search_link_kw = st.text_input("Тема", value="Digital Asset Management")
        if st.button("Найти URL", type="primary"):
            found_pages = retrieve_linking_pages(search_link_kw, selected_product, top_k=8)
            for fp in found_pages:
                with st.container(border=True):
                    st.markdown(f"**[{fp.get('title','')}]({fp.get('url','')})** {get_score_badge(fp.get('similarity',0))}", unsafe_allow_html=True)

# 5. BATCH
elif st.session_state.active_tab.startswith("⚡ Batch"):
    with st.container(border=True):
        st.markdown("#### ⚡ Пакетная генерация")
        batch_input = st.text_area("Ключи (по одному на строку)")
        batch_type = st.selectbox("Формат", ["Meta Title + Description", "SEO Article Section"])
        if st.button("🚀 Запустить", type="primary"):
            keywords = [k.strip() for k in batch_input.split("\n") if k.strip()]
            results = []
            bar = st.progress(0)
            for i, kw in enumerate(keywords):
                f_ctx = "\n".join([f"- {f.get('claim','')}" for f in retrieve_facts(kw, selected_product, top_k=4)])
                txt = generate_llm(f"Напиши {batch_type} для {selected_product} по теме '{kw}'. Факты:\n{f_ctx}")
                doc = generate_llm(f"Проверка галлюцинаций. Статус PASS или FAIL.\n{txt}")
                save_generation_to_history(selected_product, st.session_state["username"], kw, batch_type, txt, doc)
                results.append({"Ключ": kw, "Текст": txt, "Статус": "✅ PASS" if "PASS" in doc.upper() else "❌ FAIL"})
                bar.progress((i + 1) / len(keywords))
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)

# 6. ИСТОРИЯ
elif st.session_state.active_tab.startswith("📜 История"):
    with st.container(border=True):
        hist_data = get_content_history(selected_product)
        if hist_data:
            df = pd.DataFrame(hist_data)
            st.dataframe(df[["created_at", "target_keyword", "status"]], hide_index=True, use_container_width=True)
            sel_id = st.selectbox("Лог:", df["id"].tolist())
            row = next(r for r in hist_data if r["id"] == sel_id)
            st.markdown(row["generated_text"])
            st.info(row.get('doctor_verdict',''))
