import os
import json
import re
import xml.etree.ElementTree as ET
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

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

# Разбиваем строку, чтобы предотвратить баг с гиперссылками при копировании
GEMINI_API_BASE = "https" + "://generativelanguage.googleapis.com/v1beta/models"

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

# --- CUSTOM CSS ---
st.markdown("""
<style>
    [data-testid="stSidebar"] .stButton > button {
        justify-content: flex-start !important;
        padding-left: 15px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #2E6BFF !important; 
        color: #FFFFFF !important; 
        border: none !important; 
        font-weight: 600 !important; 
        border-radius: 6px !important; 
        transition: all 0.2s ease;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1A54DF !important; 
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background-color: transparent !important; 
        color: var(--text-color) !important; 
        border: 1px solid transparent !important; 
        font-weight: 500 !important;
        border-radius: 6px !important;
        opacity: 0.85;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background-color: rgba(128, 128, 128, 0.12) !important; 
        opacity: 1;
    }
    .badge-green { background-color: rgba(46, 133, 64, 0.15); color: #2E7D32; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(46, 133, 64, 0.3); }
    .badge-yellow { background-color: rgba(245, 158, 11, 0.15); color: #D97706; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-red { background-color: rgba(239, 68, 68, 0.15); color: #DC2626; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-neutral { background-color: rgba(128, 128, 128, 0.1); color: var(--text-color); padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; }
    .qa-box { background-color: rgba(46, 133, 64, 0.05); border-left: 5px solid #2E7D32; padding: 15px; border-radius: 6px; margin-top: 15px; }
    [data-testid="stSidebar"] [data-testid="stImage"] img {
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
    }
</style>
""", unsafe_allow_html=True)

# Функция для защиты от багов с LaTeX (экранирует знаки доллара)
def safe_md(text):
    if not isinstance(text, str): return text
    return text.replace('$', '\\$')

def get_score_badge(score):
    if score >= 0.65: return f"<span class='badge-green'>{score:.2f}</span>"
    elif score >= 0.45: return f"<span class='badge-yellow'>{score:.2f}</span>"
    else: return f"<span class='badge-red'>{score:.2f}</span>"

def get_relative_time(date_str):
    if not date_str or str(date_str).lower() == "none": return "—"
    try:
        past = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        s = (now - past).total_seconds()
        if s < 60: return "just now"
        elif s < 3600: return f"{int(s//60)}m ago"
        elif s < 86400: return f"{int(s//3600)}h ago"
        else: return f"{int(s//86400)}d ago"
    except: return str(date_str)[:10]

def clean_json_string(raw_text):
    text = raw_text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

def get_supabase_headers(): 
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

# --- ФЕТЧИНГ ПРОЕКТОВ ---
@st.cache_data(ttl=60)
def fetch_projects():
    default_projects = [{"project_name": "Pics.io (DAM)", "domain": "pics.io"}, {"project_name": "Toriut (PIM)", "domain": "toriut"}]
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/seo_projects?select=*", headers=get_supabase_headers(), timeout=5)
        if res.status_code == 200 and res.json():
            return res.json()
    except: pass
    return default_projects

all_projects = fetch_projects()
project_options = {p["domain"]: p["project_name"] for p in all_projects}
project_domains = list(project_options.keys())

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None

if not st.session_state["authenticated"]:
    with st.container(border=True):
        st.markdown("### 🔐 System Login")
        col1, _ = st.columns([1, 2])
        with col1:
            user_input = st.text_input("User")
            pass_input = st.text_input("Password", type="password")
            if st.button("Log In", type="primary"):
                u = user_input.strip().lower()
                p = pass_input.strip()
                if u in AUTH_USERS and AUTH_USERS[u] == p:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = u
                    st.rerun()
                else:
                    st.error("Invalid credentials")
    st.stop()

# --- САЙДБАР ---
with st.sidebar:
    st.write("") 
    if "selected_product" not in st.session_state or st.session_state.selected_product not in project_domains:
        st.session_state.selected_product = project_domains[0] if project_domains else "pics.io"
        
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        try:
            if st.session_state.selected_product == "pics.io": 
                st.image("picsio_logo.jpeg", use_container_width=True)
            elif st.session_state.selected_product == "toriut": 
                st.image("toriut_logo.jpeg", use_container_width=True)
        except Exception: 
            pass
            
    st.write("")
    
    st.markdown("<p style='font-size:0.8em; font-weight:700; opacity:0.6; letter-spacing:1px; margin-bottom:5px;'>ACTIVE PROJECT</p>", unsafe_allow_html=True)
    selected_product = st.selectbox(
        "Продукт",
        options=project_domains,
        format_func=lambda x: project_options.get(x, x),
        key="selected_product",
        label_visibility="collapsed"
    )
    
    with st.expander("+ Add New Project"):
        new_p_name = st.text_input("Project Name", placeholder="MyProduct (SaaS)")
        new_p_domain = st.text_input("Domain", placeholder="myproduct.com")
        if st.button("Create Project", use_container_width=True):
            if new_p_name and new_p_domain:
                requests.post(f"{SUPABASE_URL}/rest/v1/seo_projects", headers=get_supabase_headers(), json={"project_name": new_p_name, "domain": new_p_domain})
                st.cache_data.clear()
                st.rerun()
        
    st.divider()

    st.markdown(f"User: <span class='badge-neutral'>{st.session_state['username']}</span>", unsafe_allow_html=True)
    if st.button("Log Out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["username"] = None
        st.rerun()
    
    st.write("")
    st.markdown("<p style='opacity: 0.6; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:10px;'>MODULES</p>", unsafe_allow_html=True)
    
    menu_items = [
        "✍️ Генерация + Доктор",
        "📊 Gap Audit",
        "🌐 Link Checker",
        "👥 База доноров",
        "🎯 Insertion Planner",
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
            if "edit_link_id" in st.session_state: st.session_state.edit_link_id = None
            if "gap_active" in st.session_state: st.session_state.gap_active = False 
            st.rerun()
    
    st.divider()
    gemini_key_input = st.text_input("Gemini API Key", value=DEFAULT_GEMINI_KEY, type="password")
    CURRENT_KEY = gemini_key_input.strip().strip("'").strip('"')

# --- ЖЕЛЕЗОБЕТОННЫЙ РЕЗОЛВЕР МОДЕЛЕЙ И API ---
@st.cache_data(ttl=3600, show_spinner=False)
def resolve_models(api_key):
    if not api_key: return None, None, "Укажите Gemini API Key"
    try:
        url = f"{GEMINI_API_BASE}?key={api_key}"
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
            for pref in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-pro", "gemini-3.0-flash", "gemini-2.5-flash"]:
                for c in gen_cands:
                    if pref in c: gen_m = c; break
                if gen_m: break
            
            if not gen_m:
                for c in gen_cands:
                    if "flash" in c and "lite" not in c.lower(): gen_m = c; break
            
            if not gen_m and gen_cands: gen_m = gen_cands[0]

            return embed_m or "models/text-embedding-004", gen_m or "models/gemini-3.8-flash", "OK"
        else: return None, None, f"Код ошибки: {res.status_code}"
    except Exception as e: return "models/text-embedding-004", "models/gemini-3.8-flash", f"Fallback: {e}"

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

def get_embedding(text: str):
    if not CURRENT_KEY or not EMBED_MODEL: return None
    clean_model = EMBED_MODEL.replace('models/', '')
    try:
        url = f"{GEMINI_API_BASE}/{clean_model}:embedContent?key={CURRENT_KEY}"
        res = requests.post(url, json={"content": {"parts": [{"text": text}]}}, timeout=10)
        if res.status_code == 200: return res.json()["embedding"]["values"][:768]
    except: pass
    return None

def generate_llm(prompt: str, temperature: float = 0.2):
    if not CURRENT_KEY or not GEN_MODEL: return "Ошибка: API Key."
    clean_model = GEN_MODEL.replace('models/', '')
    try:
        url = f"{GEMINI_API_BASE}/{clean_model}:generateContent?key={CURRENT_KEY}"
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}, timeout=30)
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

def shorten_url(url, max_len=30):
    if not url or str(url) == "#" or str(url).lower() == "none": return "—"
    clean = str(url).replace("https://", "").replace("http://", "").replace("www.", "")
    if len(clean) > max_len: return clean[:max_len] + "..."
    return clean

def check_link_status(page_url, target_url, target_keyword):
    status_code = 0
    attr_result = "Not Found"
    safe_t_url = str(target_url).lower().strip() if target_url else ""
    safe_t_kw = str(target_keyword).lower().strip() if target_keyword else ""
    t_url_lower = safe_t_url if safe_t_url not in ["none", "#", "—", ""] else ""
    t_kw_lower = safe_t_kw if safe_t_kw not in ["none", "#", "—", ""] else ""
    
    try:
        resp = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        status_code = resp.status_code
        if status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            found_url, found_exact = False, False
            for a in soup.find_all('a', href=True):
                href_val = a['href'].lower()
                txt_val = a.get_text().strip().lower()
                url_match = (t_url_lower in href_val) if t_url_lower else True
                kw_match = (t_kw_lower in txt_val or t_kw_lower in href_val) if t_kw_lower else True
                if url_match:
                    found_url = True
                    if kw_match:
                        found_exact = True
                        attr_result = "nofollow" if 'nofollow' in [r.lower() for r in a.get('rel', [])] else "dofollow"
                        break
            if not found_url: attr_result = "Link Missing"
            elif found_url and not found_exact: attr_result = "Wrong Anchor"
        else: attr_result = f"HTTP Error {status_code}"
    except Exception:
        attr_result = "Error"
    return status_code, attr_result


# --- MAIN CONTENT AREA ---
st.title(st.session_state.active_tab.split(" (")[0])

# 1. ГЕНЕРАЦИЯ + ДОКТОР
if st.session_state.active_tab.startswith("✍️ Генерация"):
    if "gen_step" not in st.session_state: st.session_state.gen_step = 0
    if "gen_facts" not in st.session_state: st.session_state.gen_facts = []
    if "gen_pages" not in st.session_state: st.session_state.gen_pages = []

    with st.container(border=True):
        st.markdown("#### Настройка генерации RAG-контента")
        col1, col2 = st.columns([1, 1])
        default_kw = "Toriut Shopify integration features" if selected_product == "toriut" else "Google Drive DAM integration features"
        with col1: target_kw = st.text_input("Целевой ключевой запрос", value=default_kw)
        with col2: content_type = st.selectbox("Тип контента", ["Feature Landing Page", "SEO Article Section", "Meta Title + Description + FAQ"])
        
        with st.expander("⚙️ Расширенные настройки"):
            c1, c2 = st.columns(2)
            top_k = c1.slider("Количество фактов из базы", 2, 12, 6)
            top_links_count = c2.slider("Количество внутренних ссылок", 1, 6, 3)
            
        if st.button("🔍 Найти факты в базе", type="primary", use_container_width=True):
            with st.spinner("Сбор данных..."):
                st.session_state.gen_facts = retrieve_facts(target_kw, selected_product, top_k=top_k)
                st.session_state.gen_pages = retrieve_linking_pages(target_kw, selected_product, top_k=top_links_count)
                st.session_state.gen_step = 1

    if st.session_state.gen_step >= 1:
        st.divider()
        st.markdown("#### 1. QA: Проверка фактов (Human-in-the-loop)")
        st.caption("Отметьте только те факты, которые нужны для генерации. Вы можете отредактировать их прямо в ячейке.")
        
        df_facts = pd.DataFrame(st.session_state.gen_facts)
        if not df_facts.empty and 'claim' in df_facts.columns:
            display_df = df_facts[['claim', 'similarity']].copy()
            display_df.insert(0, "Использовать", True)
            
            edited_facts = st.data_editor(
                display_df,
                column_config={
                    "Использовать": st.column_config.CheckboxColumn("☑️", default=True),
                    "claim": st.column_config.TextColumn("Факт из базы (можно менять)", width="large"),
                    "similarity": st.column_config.NumberColumn("Сходство", format="%.2f", disabled=True)
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.warning("Факты не найдены.")
            edited_facts = pd.DataFrame()

        with st.container(border=True):
            st.markdown("#### 2. Запуск генерации")
            c_t, c_f, _ = st.columns([1, 1, 1])
            tov = c_t.selectbox("Tone of Voice", ["Professional & Authoritative", "Casual & Friendly", "Tech-heavy / Academic"])
            fmt = c_f.selectbox("Формат вывода", ["Markdown", "HTML", "Plain Text"])
            
            if st.button("🚀 Сгенерировать контент", type="primary", use_container_width=True):
                if not edited_facts.empty:
                    selected_facts = edited_facts[edited_facts["Использовать"]]["claim"].tolist()
                else:
                    selected_facts = []

                if not selected_facts:
                    st.error("Выберите хотя бы один факт для генерации!")
                else:
                    c_res, c_doc = st.columns([1.5, 1])
                    
                    with c_res:
                        with st.container(border=True):
                            st.markdown("#### ✨ Готовый контент")
                            with st.spinner("LLM пишет текст..."):
                                facts_context = "\n".join([f"- {f}" for f in selected_facts])
                                links_context = "\n".join([f"- [{p.get('title','')}]({p.get('url','')})" for p in st.session_state.gen_pages]) if st.session_state.gen_pages else "Отсутствуют"
                                
                                gen_prompt = f"""Ты — Senior SEO-копирайтер для {selected_product}.
Напиши '{content_type}' под запрос '{target_kw}'.
Формат: {fmt}
Тональность: {tov}

Строгие правила:
1. ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ ФАКТЫ (0% отсебятины):
{facts_context}

2. Органично вставь 1-2 из этих внутренних ссылок:
{links_context}"""
                                generated_text = generate_llm(gen_prompt, temperature=0.2)
                                st.markdown(safe_md(generated_text))
                                st.download_button("📥 Скачать файл (.md)", data=generated_text, file_name=f"{target_kw.replace(' ','_')}.md", mime="text/markdown")

                    with c_doc:
                        with st.container(border=True):
                            st.markdown("#### 🩺 Умный Доктор (QA Verification)")
                            with st.spinner("Анализ на галлюцинации..."):
                                doc_prompt = f"""Проанализируй текст на соответствие фактам. Ищи галлюцинации.
ФАКТЫ В БАЗЕ:
{facts_context}

СГЕНЕРИРОВАННЫЙ ТЕКСТ:
{generated_text}

Формат ответа:
Вердикт: PASS или FAIL.
Если FAIL, выпиши конкретные цитаты с отсебятиной и объясни, почему это галлюцинация.
Если PASS, подтверди, что текст на 100% безопасен."""
                                doc_verdict = generate_llm(doc_prompt, temperature=0.0)
                                
                                if "PASS" in doc_verdict.upper() and "FAIL" not in doc_verdict.upper():
                                    st.markdown(f"<div style='background-color:rgba(46,133,64,0.1); padding:10px; border-radius:6px; border-left: 4px solid #2E7D32;'>{safe_md(doc_verdict)}</div>", unsafe_allow_html=True)
                                    st.markdown(f"<div class='qa-box'><b>🛡️ Quality Assurance:</b><br>Текст проверен нейросетью и верифицирован специалистом <b>@{st.session_state['username']}</b>. <br>✅ Готово к публикации.</div>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<div style='background-color:rgba(239,68,68,0.1); padding:10px; border-radius:6px; border-left: 4px solid #DC2626;'>{safe_md(doc_verdict)}</div>", unsafe_allow_html=True)
                                    st.markdown(f"<div class='qa-box' style='border-left-color: #DC2626; background-color: rgba(239, 68, 68, 0.05);'><b>❌ QA Rejected:</b><br>Текст не прошел внутреннюю проверку на достоверность. Требуется регенерация.</div>", unsafe_allow_html=True)
                                
                                save_generation_to_history(selected_product, st.session_state["username"], target_kw, content_type, generated_text, doc_verdict)


# 2. GAP AUDIT
elif st.session_state.active_tab.startswith("📊 Gap"):
    st.info("💡 **Как это работает:** Введите поисковый запрос (интент), под который планируете писать. Система просканирует базу знаний и покажет Score (покрытие фактами). Если покрытие слабое — создаст ТЗ для автора.")
    
    tab_single, tab_batch = st.tabs(["🔍 Одиночный аудит", "📁 Массовый аудит (Batch)"])
    
    with tab_single:
        with st.container(border=True):
            default_audit = f"How {selected_product} pricing and limits work?" if selected_product == "toriut" else f"Can {selected_product} integrate with HubSpot?"
            audit_kw = st.text_input("Поисковый запрос на слепые зоны", value=default_audit)
            run_audit = st.button("Провести аудит", type="primary")

        if run_audit:
            with st.spinner("Векторный анализ базы..."):
                audit_facts = retrieve_facts(audit_kw, selected_product, top_k=4, threshold=0.0)
                pages_to_update = retrieve_linking_pages(audit_kw, selected_product, top_k=3)
                
                best_sc = audit_facts[0].get("similarity", 0) if audit_facts else 0
                p_score = int(best_sc * 100)
                if p_score > 100: p_score = 100
                
                if p_score >= 65: color, text_s = "#10B981", "Отличное покрытие"
                elif p_score >= 45: color, text_s = "#F59E0B", "Среднее покрытие"
                else: color, text_s = "#EF4444", "Слепая зона"

                dash_html = f"""
                <div style="display:flex; justify-content: center; margin-bottom: 20px;">
                    <div style="position:relative; width:180px; height:90px; overflow:hidden;">
                        <div style="width:180px; height:180px; border-radius:50%; background: conic-gradient({color} {p_score/2}%, rgba(128,128,128,0.2) 0); transform: rotate(-90deg);"></div>
                        <div style="position:absolute; top:15px; left:15px; width:150px; height:150px; border-radius:50%; background-color: var(--background-color, #ffffff); opacity: 0.05;"></div> 
                        <div style="position:absolute; top:40px; left:0; width:100%; text-align:center; color: var(--text-color);">
                            <span style="font-size:32px; font-weight:bold;">{p_score}%</span><br>
                            <span style="font-size:12px; font-weight:bold; color:{color};">{text_s}</span>
                        </div>
                    </div>
                </div>
                """
                
                facts_text = "".join([f"- {af.get('claim','')}\n" for af in audit_facts]) if audit_facts else "Фактов в базе НЕТ."
                pages_text = "".join([f"- {pu.get('url', '')}\n" for pu in pages_to_update]) if pages_to_update else "Релевантных страниц НЕТ."
                
                matrix_prompt = f"""Проанализируй интент '{audit_kw}' для продукта '{selected_product}'.
Найденные фрагменты в базе:
{facts_text}
Ближайшие существующие URL: {pages_text}

Твоя задача — дать ответ из ДВУХ частей, разделенных ровно строкой "===MATRIX===".

ЧАСТЬ 1 (Аналитика текста):
Напиши развернутый анализ в формате Markdown:
1. 🎯 Вердикт по интенту: Насколько текущая база закрывает боль пользователя?
2. 🚨 Слепые зоны: Чего критически не хватает?
3. 🛠 Actionable Advice: Что конкретно нужно сделать с контентом.

===MATRIX===

ЧАСТЬ 2 (JSON таблица):
Верни СТРОГО валидный JSON-массив объектов. Никакого текста, только массив. Ключи:
"sub_topic" (строка, название подтемы),
"status" (строка, "Есть в базе" или "Слепая зона"),
"recommendation" (строка, что конкретно написать),
"target_url" (строка, URL из ближайших или 'Новая страница'),
"business_value" (строка, выгода/ROI).
"""
                raw_ans = generate_llm(matrix_prompt, temperature=0.1)
                
                if "===MATRIX===" in raw_ans:
                    strat_text, raw_json = raw_ans.split("===MATRIX===", 1)
                elif "```json" in raw_ans:
                    parts = raw_ans.split("```json", 1)
                    strat_text = parts[0].strip()
                    raw_json = "```json\n" + parts[1]
                else:
                    strat_text = raw_ans
                    raw_json = "[]"
                    
                clean_json = clean_json_string(raw_json)
                
                st.session_state.gap_dash_html = dash_html
                st.session_state.gap_strategy_text = strat_text.strip()
                st.session_state.gap_matrix = clean_json
                st.session_state.gap_kw = audit_kw
                st.session_state.gap_active = True

        if st.session_state.get("gap_active"):
            st.markdown(st.session_state.gap_dash_html, unsafe_allow_html=True)
            
            st.markdown("#### 🕵️ Пруфы аудита (Стратегия)")
            st.info(safe_md(st.session_state.gap_strategy_text))

            st.divider()
            
            if st.button("📝 Создать Jira-ready ТЗ копирайтеру", type="primary"):
                with st.spinner("Генерация ТЗ..."):
                    brief_prompt = f"""Сгенерируй детальное ТЗ для копирайтера под запрос '{st.session_state.gap_kw}' на основе матрицы пробелов:
{st.session_state.gap_matrix}

Сформируй ответ так, чтобы его можно было сразу скопировать в таск-трекер (Jira/Trello).
Используй структуру:
**Task Title:** Написать/Обновить статью под запрос [{st.session_state.gap_kw}]
**Business Value (Зачем мы это делаем):** [кратко из матрицы]
**Description / Structure:** [детальный план H2/H3]
**Required Entities (LSI):** [какие термины обязательно использовать]
**Acceptance Criteria (DoD):** [чек-лист для проверки качества]
"""
                    brief = generate_llm(brief_prompt, temperature=0.3)
                    st.markdown("#### 📋 Готовый тикет (ТЗ)")
                    st.markdown(safe_md(brief))
                    st.download_button("📥 Скачать ТЗ (.md)", data=brief, file_name=f"Jira_Task_{st.session_state.gap_kw.replace(' ','_')}.md", mime="text/markdown")

            st.divider()

            try:
                matrix_data = json.loads(st.session_state.gap_matrix)
                if matrix_data:
                    st.markdown("#### 📊 Матрица контента и ROI")
                    st.caption("Детализация контент-плана по сущностям (для Тимлида/Менеджера).")
                    df_matrix = pd.DataFrame(matrix_data)
                    st.dataframe(df_matrix, hide_index=True, use_container_width=True)
            except Exception as e:
                st.warning("Таблица матрицы не сгенерировалась (LLM вернула нестандартный формат).")

    with tab_batch:
        with st.container(border=True):
            st.markdown("#### Массовый поиск слепых зон")
            batch_kws = st.text_area("Ключи (каждый с новой строки)", placeholder="Shopify integration\nGoogle Drive limits")
            if st.button("🚀 Запустить Batch Audit", type="primary"):
                kws = [k.strip() for k in batch_kws.split("\n") if k.strip()]
                results = []
                bar = st.progress(0)
                for i, kw in enumerate(kws):
                    facts = retrieve_facts(kw, selected_product, top_k=1)
                    if facts:
                        sc = facts[0].get("similarity", 0)
                        p_sc = int(sc * 100)
                        status = "🟢 Закрыто" if p_sc >= 65 else ("🟡 Средне" if p_sc >= 45 else "🔴 Слепая зона")
                    else:
                        p_sc, status = 0, "🔴 Слепая зона"
                    results.append({"Ключ (Интент)": kw, "Score": f"{p_sc}%", "Статус": status})
                    bar.progress((i+1)/len(kws))
                st.dataframe(pd.DataFrame(results).sort_values(by="Score"), hide_index=True, use_container_width=True)

# 3. LINK CHECKER
elif st.session_state.active_tab.startswith("🌐 Link Checker"):
    with st.container(border=True):
        st.markdown(f"#### 🌐 Мониторинг бэклинков ({selected_product.upper()})")
        
        with st.expander("➕ Добавить / Импорт бэклинков"):
            tab_single, tab_batch = st.tabs(["Добавить одну ссылку", "Загрузить из файла (CSV / TXT)"])
            single_to_add = None
            batch_items = []
            with tab_single:
                col_s1, col_s2, col_s3 = st.columns([1.5, 1.5, 1])
                with col_s1: single_url = st.text_input("URL статьи (донор)", key="s_u_i")
                with col_s2: single_target = st.text_input("Куда ссылаемся (Target URL)", key="s_t_i")
                with col_s3: single_kw = st.text_input("Ключ / Бренд", key="s_k_i")
                if st.button("Проверить и сохранить", type="primary"):
                    if single_url.strip() and single_target.strip() and single_kw.strip(): single_to_add = (single_url.strip(), single_target.strip(), single_kw.strip())
                    else: st.warning("Заполните все поля.")
            with tab_batch:
                uploaded_links_file = st.file_uploader("Формат: URL статьи, Target URL, Ключ", type=["csv", "txt"])
                if st.button("Запустить массовую проверку", type="primary"):
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
            queue_to_process.extend(batch_items)

            if queue_to_process:
                bar = st.progress(0)
                success_cnt = 0
                for idx, (url_to_check, target_url, target_brand) in enumerate(queue_to_process):
                    status_code, attr_result = check_link_status(url_to_check, target_url, target_brand)
                    payload = {"product": selected_product, "page_url": url_to_check, "target_url": target_url, "target_keyword": target_brand, "http_status": status_code, "link_attribute": attr_result}
                    try: 
                        requests.post(f"{SUPABASE_URL}/rest/v1/link_checker", headers=get_supabase_headers(), json=payload, timeout=5)
                        success_cnt += 1
                    except: pass
                    bar.progress((idx + 1) / len(queue_to_process))
                st.success(f"Готово! Сохранено: {success_cnt}")
                st.rerun()

        st.divider()

        r_links = requests.get(f"{SUPABASE_URL}/rest/v1/link_checker?product=eq.{selected_product}&order=checked_at.desc", headers=get_supabase_headers(), timeout=10)
        if r_links.status_code == 200 and r_links.json():
            links_data = r_links.json()
            df = pd.DataFrame(links_data)
            
            df['is_live'] = (df['http_status'] == 200) & (df['link_attribute'].isin(['dofollow', 'nofollow']))
            df['Status'] = df['is_live'].apply(lambda x: "🟢 Live" if x else "🔴 Dead")
            df['Anchor & Target'] = df.apply(lambda r: f"{r.get('target_keyword') or '—'} \n {r.get('target_url') or '#'}", axis=1)
            df['Checked'] = df['checked_at'].apply(get_relative_time)
            df['Select'] = False
            
            total_links = len(df)
            live_links = df['is_live'].sum()
            dofollow_links = len(df[df['link_attribute'] == 'dofollow'])
            
            p_live = int((live_links / total_links) * 100) if total_links else 0
            p_dof = int((dofollow_links / total_links) * 100) if total_links else 0
            
            dash_html = f"""
            <div style="display:flex; justify-content: space-around; margin-bottom: 30px; flex-wrap: wrap;">
                <div style="position:relative; width:130px; height:130px;">
                    <div style="width:100%; height:100%; border-radius:50%; background: conic-gradient(#3B82F6 100%, rgba(128,128,128,0.2) 0); -webkit-mask-image: radial-gradient(transparent 55%, black 56%); mask-image: radial-gradient(transparent 55%, black 56%);"></div>
                    <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color: var(--text-color);">
                        <span style="font-size:28px; font-weight:bold;">{total_links}</span>
                        <span style="font-size:12px; opacity:0.7;">Total Links</span>
                    </div>
                </div>
                <div style="position:relative; width:130px; height:130px;">
                    <div style="width:100%; height:100%; border-radius:50%; background: conic-gradient(#10B981 {p_live}%, rgba(128,128,128,0.2) 0); -webkit-mask-image: radial-gradient(transparent 55%, black 56%); mask-image: radial-gradient(transparent 55%, black 56%);"></div>
                    <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color: var(--text-color);">
                        <span style="font-size:28px; font-weight:bold;">{live_links}</span>
                        <span style="font-size:12px; opacity:0.7;">Live ({p_live}%)</span>
                    </div>
                </div>
                <div style="position:relative; width:130px; height:130px;">
                    <div style="width:100%; height:100%; border-radius:50%; background: conic-gradient(#10B981 {p_dof}%, rgba(128,128,128,0.2) 0); -webkit-mask-image: radial-gradient(transparent 55%, black 56%); mask-image: radial-gradient(transparent 55%, black 56%);"></div>
                    <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color: var(--text-color);">
                        <span style="font-size:28px; font-weight:bold;">{dofollow_links}</span>
                        <span style="font-size:12px; opacity:0.7;">Dofollow</span>
                    </div>
                </div>
                <div style="position:relative; width:130px; height:130px;">
                    <div style="width:100%; height:100%; border-radius:50%; background: conic-gradient(#EF4444 {100-p_live}%, rgba(128,128,128,0.2) 0); -webkit-mask-image: radial-gradient(transparent 55%, black 56%); mask-image: radial-gradient(transparent 55%, black 56%);"></div>
                    <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color: var(--text-color);">
                        <span style="font-size:28px; font-weight:bold;">{total_links - live_links}</span>
                        <span style="font-size:12px; opacity:0.7;">Dead / Missing</span>
                    </div>
                </div>
            </div>
            """
            st.markdown(dash_html, unsafe_allow_html=True)
            
            f1, f2, f3 = st.columns([2, 1, 1])
            search_q = f1.text_input("🔍 Поиск", placeholder="Поиск по URL страницы донора...")
            status_f = f2.multiselect("Статус", ["🟢 Live", "🔴 Dead"], default=["🟢 Live", "🔴 Dead"])
            attr_f = f3.multiselect("Атрибут", ["dofollow", "nofollow", "Link Missing", "Wrong Anchor", "Not Found", "Error"], default=["dofollow", "nofollow", "Link Missing", "Wrong Anchor", "Not Found", "Error"])
            
            if search_q: df = df[df['page_url'].str.contains(search_q, case=False)]
            df = df[df['Status'].isin(status_f)]
            df = df[df['link_attribute'].isin(attr_f)]
            
            st.write("")
            
            display_df = df[['Select', 'id', 'page_url', 'Anchor & Target', 'Status', 'link_attribute', 'http_status', 'Checked']]
            edited_df = st.data_editor(
                display_df,
                column_config={
                    "Select": st.column_config.CheckboxColumn("☑️", default=False),
                    "id": None,
                    "page_url": st.column_config.LinkColumn("Referring Page", display_text=r"https?://(?:www\.)?([^/]+).*"), 
                    "Anchor & Target": st.column_config.TextColumn("Backlink Anchor & URL"),
                    "Status": st.column_config.TextColumn("Active"),
                    "link_attribute": st.column_config.TextColumn("Rel Attribute"),
                    "http_status": st.column_config.NumberColumn("HTTP"),
                    "Checked": st.column_config.TextColumn("Indexed / Checked")
                },
                disabled=["page_url", "Anchor & Target", "Status", "link_attribute", "http_status", "Checked"],
                hide_index=True, use_container_width=True
            )
            
            selected_rows = edited_df[edited_df['Select']]
            selected_ids = selected_rows['id'].tolist()
            
            if len(selected_ids) == 1:
                row_to_edit = selected_rows.iloc[0]
                orig_data = df[df['id'] == row_to_edit['id']].iloc[0]
                with st.expander("✏️ Редактировать выбранную ссылку", expanded=True):
                    ce1, ce2, ce3 = st.columns(3)
                    e_p_url = ce1.text_input("URL донора", value=orig_data['page_url'])
                    e_t_url = ce2.text_input("Цель (наш сайт)", value=orig_data['target_url'] if orig_data['target_url'] else "")
                    e_kw = ce3.text_input("Ключ / Анкор", value=orig_data['target_keyword'] if orig_data['target_keyword'] else "")
                    
                    if st.button("💾 Сохранить и Перепроверить", type="primary"):
                        s_code, a_res = check_link_status(e_p_url, e_t_url, e_kw)
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{row_to_edit['id']}", 
                            headers=get_supabase_headers(), 
                            json={"page_url": e_p_url, "target_url": e_t_url, "target_keyword": e_kw, "http_status": s_code, "link_attribute": a_res}
                        )
                        st.rerun()

            if len(selected_ids) > 0:
                ca1, ca2 = st.columns([1, 5])
                if ca1.button("🗑️ Удалить", type="primary"):
                    for rid in selected_ids: requests.delete(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{rid}", headers=get_supabase_headers())
                    st.rerun()
                if ca2.button("🔄 Перепроверить", type="secondary"):
                    with st.spinner("Идет парсинг ссылок..."):
                        for rid in selected_ids:
                            orig_data = df[df['id'] == rid].iloc[0]
                            s_code, a_res = check_link_status(orig_data['page_url'], orig_data['target_url'], orig_data['target_keyword'])
                            requests.patch(f"{SUPABASE_URL}/rest/v1/link_checker?id=eq.{rid}", headers=get_supabase_headers(), json={"http_status": s_code, "link_attribute": a_res})
                    st.rerun()
                    
            st.write("")
            st.download_button("📥 Экспорт всей базы в CSV", data=pd.DataFrame(links_data).to_csv(index=False).encode('utf-8'), file_name=f"links_dashboard_{selected_product}.csv", mime="text/csv")
            
        else:
            st.info(f"База бэклинков для {selected_product.upper()} пока пуста или недоступна.")

# 4. БАЗА ДОНОРОВ (CRM)
elif st.session_state.active_tab.startswith("👥 База"):
    with st.container(border=True):
        st.markdown(f"#### База доноров ({selected_product.upper()})")
        with st.expander("+ Добавить донора", expanded=False):
            c1, c2 = st.columns(2)
            d_domain = c1.text_input("Сайт донора (Domain)", placeholder="example.com")
            d_type = c2.selectbox("Способ связи", ["Email", "LinkedIn", "Сайт (Форма)", "Slack/Community", "Other"])
            c3, c4 = st.columns(2)
            d_contact = c3.text_input("Контакт (Email / Ссылка)", placeholder="editor@example.com")
            d_collab = c4.selectbox("Тип сотрудничества", ["Обмен (Link Exchange)", "Гостевой пост", "Покупка (Paid)", "Органика"])
            d_notes = st.text_input("Заметки", placeholder="Требуют DR 50+, готовы меняться 1 к 1")
            
            if st.button("Сохранить донора", type="primary"):
                if d_domain:
                    payload = {"project": selected_product, "domain": d_domain, "contact_type": d_type, "contact_info": d_contact, "collab_type": d_collab, "notes": d_notes}
                    requests.post(f"{SUPABASE_URL}/rest/v1/link_donors", headers=get_supabase_headers(), json=payload)
                    st.success("Донор добавлен!")
                    st.rerun()

        st.divider()
        try:
            r_donors = requests.get(f"{SUPABASE_URL}/rest/v1/link_donors?project=eq.{selected_product}&order=created_at.desc", headers=get_supabase_headers(), timeout=5)
            if r_donors.status_code == 200 and r_donors.json():
                donors_data = r_donors.json()
                st.markdown("#### Список партнеров")
                
                items_per_page = 10
                total_pages = max(1, (len(donors_data) + items_per_page - 1) // items_per_page)
                if "donor_page" not in st.session_state: st.session_state.donor_page = 1
                if st.session_state.donor_page > total_pages: st.session_state.donor_page = total_pages
                
                start_idx = (st.session_state.donor_page - 1) * items_per_page
                page_data = donors_data[start_idx : start_idx + items_per_page]

                hc = st.columns([1.5, 1, 1.5, 1.5, 2, 0.4])
                for col, text in zip(hc, ["Домен", "Связь", "Контакт", "Тип", "Заметки", ""]): col.markdown(f"**{text}**")
                st.divider()

                for row in page_data:
                    with st.container(border=True):
                        c = st.columns([1.5, 1, 1.5, 1.5, 2, 0.4])
                        c[0].markdown(f"[{row.get('domain')}]({row.get('domain') if str(row.get('domain')).startswith('http') else 'https://'+str(row.get('domain'))})")
                        c[1].write(row.get('contact_type', '-'))
                        c[2].write(row.get('contact_info', '-'))
                        c[3].markdown(f"<span class='badge-neutral'>{row.get('collab_type', '-')}</span>", unsafe_allow_html=True)
                        c[4].write(row.get('notes', '-'))
                        if c[5].button("X", key=f"del_d_{row['id']}"):
                            requests.delete(f"{SUPABASE_URL}/rest/v1/link_donors?id=eq.{row['id']}", headers=get_supabase_headers())
                            st.rerun()
                            
                if total_pages > 1:
                    st.write("")
                    p_cols = st.columns(min(15, total_pages) + 2)
                    for p_num in range(1, total_pages + 1):
                        if p_cols[p_num-1].button(str(p_num), key=f"pag_dnr_{p_num}", type="primary" if p_num == st.session_state.donor_page else "secondary"):
                            st.session_state.donor_page = p_num; st.rerun()
        except: st.info("Нет данных")

# 5. INSERTION PLANNER
elif st.session_state.active_tab.startswith("🎯 Insertion"):
    with st.container(border=True):
        st.markdown(f"#### Планировщик ссылок ({selected_product.upper()})")
        st.caption("Анализирует текст-источник и подбирает идеальное место для органичной вставки вашей ссылки.")
        
        target_url = st.text_input("Целевая страница (наш сайт)", placeholder="https://pics.io/feature")
        target_kw = st.text_input("Ключевое слово для вставки", placeholder="digital asset management")
        insertion_mode = st.radio("Режим вставки:", ["Новое предложение (Дописать)", "Редактирование текущего (Перефразировать)", "Точное вхождение (Без изменения текста)"], horizontal=True)
        brief_text = st.text_area("Текст донора (куда вставляем ссылку)", height=150)
        
        if st.button("Сгенерировать вставки", type="primary"):
            if target_url and target_kw and brief_text.strip():
                with st.spinner("Анализ..."):
                    if "Новое предложение" in insertion_mode:
                        p_instr = f"Напиши 1-2 НОВЫХ предложения, которые логично продолжат мысль текста, и органично вставь туда анкор '{target_kw}' со ссылкой на {target_url}."
                    elif "Редактирование" in insertion_mode:
                        p_instr = f"Возьми кусок из текста, перефразируй его (если нужно) и органично встрой туда анкор '{target_kw}' со ссылкой на {target_url}."
                    else:
                        p_instr = f"Найди точное (или максимально близкое по смыслу) вхождение '{target_kw}' в тексте. Сделай его анкором на {target_url}. Не меняй оригинальный текст вокруг."
                    
                    full_prompt = f"Ты SEO Линкбилдер. Твоя задача встроить ссылку.\nРЕЖИМ: {p_instr}\n\nОРИГИНАЛЬНЫЙ ТЕКСТ ДОНОРА:\n{brief_text}\n\nВыведи готовый абзац с Markdown ссылкой, чтобы я мог скопировать и отдать контентщику."
                    res_text = generate_llm(full_prompt, temperature=0.1)
                    
                    st.write("")
                    st.markdown("<p style='font-size:1.1em; font-weight:600;'>Latest insertions</p>", unsafe_allow_html=True)
                    with st.expander(f"Target: {target_url}", expanded=True):
                        st.markdown(f"<p style='font-size: 0.85em; opacity: 0.7; margin-bottom: 15px;'>Mode: {insertion_mode} | Key: {target_kw}</p>", unsafe_allow_html=True)
                        with st.expander("DONOR CONTEXT & RESULT", expanded=True):
                            st.write(safe_md(res_text))
            else: st.warning("Заполните поля.")

# 6. ЛИНК-БИЛДЕР
elif st.session_state.active_tab.startswith("🔗 Линк"):
    with st.container(border=True):
        st.markdown("#### Векторный подбор страниц")
        search_link_kw = st.text_input("Тема для подбора URL")
        if st.button("Найти URL", type="primary"):
            found_pages = retrieve_linking_pages(search_link_kw, selected_product, top_k=8)
            for fp in found_pages:
                with st.container(border=True): st.markdown(f"[{fp.get('title','')}]({fp.get('url','')}) {get_score_badge(fp.get('similarity',0))}", unsafe_allow_html=True)

# 7. BATCH 
elif st.session_state.active_tab.startswith("⚡ Batch"):
    with st.container(border=True):
        st.markdown("#### Пакетная генерация")
        batch_input = st.text_area("Ключи (с новой строки)")
        batch_type = st.selectbox("Формат", ["Meta Title + Description", "SEO Article Section"])
        if st.button("Запустить", type="primary"):
            kws = [k.strip() for k in batch_input.split("\n") if k.strip()]
            results = []
            bar = st.progress(0)
            for i, kw in enumerate(kws):
                f_ctx = "\n".join([f"- {f.get('claim','')}" for f in retrieve_facts(kw, selected_product, top_k=4)])
                txt = generate_llm(f"Напиши {batch_type} для {selected_product}. Тема '{kw}'. Факты:\n{f_ctx}")
                doc = generate_llm(f"Проверка галлюцинаций. Статус PASS/FAIL.\nТекст: {txt}")
                save_generation_to_history(selected_product, st.session_state["username"], kw, batch_type, txt, doc)
                results.append({"Ключ": kw, "Статус": "PASS" if "PASS" in doc.upper() else "FAIL", "Текст": txt})
                bar.progress((i+1)/len(kws))
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)

# 8. ИСТОРИЯ
elif st.session_state.active_tab.startswith("📜 История"):
    with st.container(border=True):
        h_data = get_content_history(selected_product)
        if h_data:
            df = pd.DataFrame(h_data)
            st.dataframe(df[["created_at", "target_keyword", "status"]], hide_index=True, use_container_width=True)
            sel_id = st.selectbox("Лог:", df["id"].tolist())
            row = next(r for r in h_data if r["id"] == sel_id)
            st.write(safe_md(row["generated_text"]))
            st.caption(safe_md(row.get('doctor_verdict','')))
        else: st.info("Пусто")
