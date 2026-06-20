
import time
import datetime

import psutil
import streamlit as st

import jarvis as jc

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ──────────────────────────────────────────────
#  PAGE SETUP
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="J.A.R.V.I.S — Mark VII",
    page_icon="🛰️",
    layout="wide",
)

PALETTE = {
    "bg": "#000508",
    "panel": "#020d16",
    "border": "#0a2a3a",
    "dim": "#0d3348",
    "mid": "#0e6080",
    "accent": "#00c8f0",
    "bright": "#7feeff",
    "white": "#d8f8ff",
    "green": "#00ff88",
    "purple": "#aa55ff",
    "yellow": "#ffe066",
    "warn": "#ff6622",
}

MODE_COLOR = {
    "listening": "#00aaee",
    "thinking": "#aa44ff",
    "speaking": "#00ff77",
    "offline": "#445566",
}

MODE_LABEL = {
    "listening": "◉  AWAITING INPUT",
    "thinking": "◈  NEURAL PROCESSING",
    "speaking": "◈  AUDIO OUTPUT",
    "offline": "○  OFFLINE",
}

st.markdown(f"""
<style>
    .stApp {{
        background: {PALETTE['bg']};
    }}
    .block-container {{
        max-width: 1920px;
        padding-top: 1rem;
    }}
    * {{
        font-family: 'Courier New', monospace;
    }}
    .hud-panel {{
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['border']};
        border-radius: 4px;
        padding: 14px 16px;
        height: 100%;
    }}
    .hud-title {{
        color: {PALETTE['accent']};
        font-size: 0.75rem;
        font-weight: bold;
        letter-spacing: 2px;
        border-bottom: 1px solid {PALETTE['border']};
        padding-bottom: 6px;
        margin-bottom: 10px;
    }}
    .hud-row {{
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        color: {PALETTE['mid']};
        margin: 6px 0 2px 0;
    }}
    .hud-bar-bg {{
        background: {PALETTE['border']};
        height: 5px;
        border-radius: 2px;
        margin-bottom: 8px;
    }}
    .hud-bar-fill {{
        height: 5px;
        border-radius: 2px;
    }}
    .log-line {{
        font-size: 0.72rem;
        color: {PALETTE['dim']};
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        padding: 2px 0;
    }}
    .log-line.fresh {{ color: {PALETTE['accent']}; }}
    .transcript-you {{
        text-align: center;
        color: {PALETTE['mid']};
        font-size: 0.85rem;
        margin-bottom: 6px;
    }}
    .transcript-jarvis {{
        text-align: center;
        color: {PALETTE['white']};
        font-size: 1.1rem;
        font-weight: bold;
    }}
    @keyframes pulse {{
        0%   {{ box-shadow: 0 0 20px var(--glow), 0 0 40px var(--glow) inset; }}
        50%  {{ box-shadow: 0 0 55px var(--glow), 0 0 70px var(--glow) inset; }}
        100% {{ box-shadow: 0 0 20px var(--glow), 0 0 40px var(--glow) inset; }}
    }}
    .orb {{
        width: 230px;
        height: 230px;
        border-radius: 50%;
        margin: 10px auto 18px auto;
        background: radial-gradient(circle at 50% 45%, var(--glow) 0%, var(--core) 60%, #000 100%);
        border: 3px solid var(--glow);
        animation: pulse 2.4s ease-in-out infinite;
    }}
    .mode-label {{
        text-align: center;
        font-weight: bold;
        font-size: 0.95rem;
        letter-spacing: 2px;
        margin-bottom: 14px;
    }}
    div.stButton > button {{
        background: {PALETTE['panel']};
        color: {PALETTE['accent']};
        border: 1px solid {PALETTE['mid']};
        font-family: 'Courier New', monospace;
        letter-spacing: 1px;
    }}
    div.stButton > button:hover {{
        border-color: {PALETTE['accent']};
        color: {PALETTE['bright']};
    }}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
#  AUTO-REFRESH so the dashboard feels live
# ──────────────────────────────────────────────
if HAS_AUTOREFRESH:
    st_autorefresh(interval=1000, key="hud_refresh")
else:
    st.sidebar.warning(
        "Install `streamlit-autorefresh` for live updates "
        "(`pip install streamlit-autorefresh`)."
    )

# ──────────────────────────────────────────────
#  HEADER
# ──────────────────────────────────────────────
h1, h2 = st.columns([4, 1])
with h1:
    st.markdown(
        f"<div style='color:{PALETTE['accent']};font-size:1.6rem;font-weight:bold;'>"
        f"J.A.R.V.I.S <span style='color:{PALETTE['mid']};font-size:0.8rem;'>"
        f"— MARK VII · NEURAL INTERFACE</span></div>",
        unsafe_allow_html=True,
    )
with h2:
    status = "ONLINE" if jc.is_running() else "OFFLINE"
    color = PALETTE["green"] if jc.is_running() else PALETTE["warn"]
    st.markdown(
        f"<div style='text-align:right;color:{color};font-weight:bold;padding-top:10px;'>"
        f"SYS {status}</div>",
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────
#  SIDEBAR — controls
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Controls")
    if not jc.GROQ_API_KEY:
        st.error("GROQ_API_KEY isn't set. Set it as an environment variable "
                  "before starting Streamlit, then restart.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start", use_container_width=True, disabled=jc.is_running()):
            jc.start_assistant()
            st.rerun()
    with c2:
        if st.button("■ Stop", use_container_width=True, disabled=not jc.is_running()):
            jc.stop_assistant()
            st.rerun()

    st.markdown("---")
    st.markdown("### Manual command")
    st.caption("Useful for testing without speaking out loud.")
    manual = st.text_input("Type a command (no need to say 'jarvis')", key="manual_cmd")
    if st.button("Send", use_container_width=True):
        if manual.strip():
            jc.display_text["user"] = manual
            jc.log(f"Typed: {manual[:40]}")
            result = jc.handle_command(manual.lower())
            if result:
                jc.display_text["jarvis"] = result
                jc.speak(result)
            else:
                jc.current_state["mode"] = "thinking"
                reply = jc.ask_ai(manual)
                jc.display_text["jarvis"] = reply
                jc.speak(reply)
            st.rerun()

    st.markdown("---")
    if st.button("Clear memory", use_container_width=True):
        jc.clear_memory()
        st.rerun()

# ──────────────────────────────────────────────
#  MAIN LAYOUT
# ──────────────────────────────────────────────
left, center, right = st.columns([1, 1.4, 1])

# ---- LEFT: system status ----
with left:
    cpu = psutil.cpu_percent()
    mem_pct = psutil.virtual_memory().percent
    mem_msgs = len(jc.conversation_history)

    rows = [
        ("CPU LOAD", f"{cpu:.0f}%", cpu / 100, PALETTE["accent"]),
        ("RAM USAGE", f"{mem_pct:.0f}%", mem_pct / 100, PALETTE["purple"]),
        ("AI ENGINE", "LLAMA-3.3", 1.0, PALETTE["yellow"]),
        ("TTS ENGINE", "EDGE-GB", 1.0, PALETTE["accent"]),
        ("VOICE REC", "GOOGLE STT", 1.0, PALETTE["green"]),
        ("MEMORY", f"{mem_msgs} msgs", min(mem_msgs / jc.MAX_MEMORY, 1.0), PALETTE["purple"]),
    ]
    rows_html = ""
    for label, val, frac, col in rows:
        rows_html += (
            f"<div class='hud-row'><span>{label}</span><span style='color:{col};font-weight:bold;'>{val}</span></div>"
            f"<div class='hud-bar-bg'><div class='hud-bar-fill' style='width:{int(frac*100)}%;background:{col};'></div></div>"
        )

    now = datetime.datetime.now()
    st.markdown(
        f"<div class='hud-panel'><div class='hud-title'>◈ SYSTEM STATUS</div>"
        f"{rows_html}"
        f"<div style='text-align:center;margin-top:16px;color:{PALETTE['accent']};font-size:1.6rem;font-weight:bold;'>"
        f"{now.strftime('%H:%M:%S')}</div>"
        f"<div style='text-align:center;color:{PALETTE['mid']};font-size:0.75rem;'>{now.strftime('%a %d %b %Y')}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ---- CENTER: orb + transcript ----
with center:
    mode = jc.current_state.get("mode", "offline")
    glow = MODE_COLOR.get(mode, "#445566")
    label = MODE_LABEL.get(mode, "")

    st.markdown(
        f"<div class='orb' style='--glow:{glow};--core:#001018;'></div>"
        f"<div class='mode-label' style='color:{glow};'>{label}</div>",
        unsafe_allow_html=True,
    )

    u = jc.display_text.get("user", "")
    j = jc.display_text.get("jarvis", "")
    st.markdown(
        f"<div class='hud-panel'>"
        + (f"<div class='transcript-you'>YOU › {u.upper()[:120]}</div>" if u else "")
        + (f"<div class='transcript-jarvis'>JARVIS › {j[:400]}</div>" if j else
           f"<div class='transcript-jarvis' style='color:{PALETTE['mid']};'>Say "
           f"\"Jarvis\" to begin…</div>")
        + f"<div style='text-align:right;color:{PALETTE['purple']};font-size:0.7rem;margin-top:10px;'>"
        f"MEM: {len(jc.conversation_history)}/{jc.MAX_MEMORY}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ---- RIGHT: activity log ----
with right:
    lines = jc.activity_log if jc.activity_log else ["Waiting for input…"]
    log_html = ""
    for i, line in enumerate(lines[:jc.MAX_LOG]):
        cls = "fresh" if i == 0 else ""
        log_html += f"<div class='log-line {cls}'>{line}</div>"

    services = [
        ("GROQ API", bool(jc.client), PALETTE["green"]),
        ("EDGE TTS", True, PALETTE["green"]),
        ("GOOGLE STT", True, PALETTE["green"]),
        ("MEMORY DB", True, PALETTE["purple"]),
    ]
    svc_html = ""
    for name, ok, col in services:
        color = col if ok else PALETTE["warn"]
        state = "ONLINE" if ok else "OFFLINE"
        svc_html += (
            f"<div class='hud-row'><span><span style='color:{color};'>●</span> {name}</span>"
            f"<span style='color:{color};font-weight:bold;'>{state}</span></div>"
        )

    st.markdown(
        f"<div class='hud-panel'><div class='hud-title'>◈ ACTIVITY LOG</div>"
        f"{log_html}<div style='margin-top:14px;border-top:1px solid {PALETTE['border']};padding-top:10px;'>"
        f"{svc_html}</div></div>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"<div style='text-align:center;color:{PALETTE['dim']};font-size:0.7rem;margin-top:14px;'>"
    f"v8.0.0 · LLAMA-3.3-70B · EDGE-TTS · PERSISTENT MEMORY · STREAMLIT</div>",
    unsafe_allow_html=True,
)