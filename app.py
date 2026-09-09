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
</style>
""", unsafe_allow_html=True)

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
        new_p_domain =
