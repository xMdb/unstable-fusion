# app.py
# --------------------------------------------
# Streamlit Stable Diffusion Frontend
# - Login with username/password
# - Select model from list
# - Generate images (max 2 concurrent jobs)
# - Per-user gallery
# --------------------------------------------

import os
import time
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from PIL import Image

# ----------------- CONFIG --------------------
st.set_page_config(page_title="AI Image Lab", page_icon="🎨", layout="wide")
DATA_DIR = Path("generated_images")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Demo users. Replace with your own user system or DB.
DEMO_USERS = {
    "alice": "wonderland123",
    "bob": "builder123",
    "demo": "demo",
}

# Available models
MODEL_CHOICES = [
    "stabilityai/sd-turbo",
    "stable-diffusion-v1-5/stable-diffusion-v1-5",
    "CompVis/stable-diffusion-v1-4",
  #  "Envvi/Inkpunk-Diffusion",
  #  "acheong08/f222",
]

# Thread pool for up to 2 concurrent jobs
EXECUTOR = ThreadPoolExecutor(max_workers=2)

# ----------------- LOAD PIPELINE --------------------
@st.cache_resource(show_spinner=True)
def get_pipeline(model_id: str):
    import torch
    from diffusers import StableDiffusionPipeline

    try:
        torch.set_num_threads(1)
    except Exception:
        pass

    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float32
    ).to("cpu")
    return pipe

# ----------------- AUTH HELPERS --------------------
def check_password(username: str, password: str) -> bool:
    return DEMO_USERS.get(username) == password

def require_login() -> str | None:
    """Render login form if needed; return username when authenticated."""
    if "auth_user" in st.session_state and st.session_state["auth_user"]:
        return st.session_state["auth_user"]

    st.title("🎨 AI Image Lab")
    st.caption("Login to generate and browse images.")

    with st.form("login_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Username", value="", autocomplete="username")
        with col2:
            password = st.text_input("Password", value="", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in")
        if submitted:
            if check_password(username.strip(), password):
                st.session_state["auth_user"] = username.strip()
                st.success(f"Welcome, {username.strip()}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
                return None
    st.stop()

# ----------------- STORAGE HELPERS --------------------
def user_dir(username: str) -> Path:
    d = DATA_DIR / username
    d.mkdir(parents=True, exist_ok=True)
    return d

def save_image(img: Image.Image, username: str, prompt: str) -> Path:
    ts = int(time.time())
    safe_prompt = "".join(c for c in prompt.strip()[:60] if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")
    fname = f"{ts}_{safe_prompt or 'image'}.jpg"
    outpath = user_dir(username) / fname
    img.save(outpath, format="JPEG", quality=95)
    return outpath

def list_images(user: str | None = None) -> List[Path]:
    if user:
        root = user_dir(user)
        return sorted([p for p in root.glob("*.jpg")], key=os.path.getmtime, reverse=True)
    paths = []
    for sub in DATA_DIR.iterdir():
        if sub.is_dir():
            paths.extend(sub.glob("*.jpg"))
    return sorted(paths, key=os.path.getmtime, reverse=True)

# ----------------- SIDEBAR --------------------
def sidebar(username: str):
    with st.sidebar:
        st.header("👤 Account")
        st.write(f"**User:** {username}")
        if st.button("Log out", width="stretch"):
            st.session_state.pop("auth_user", None)
            st.rerun()

        st.markdown("---")
        st.header("⚙️ Generation Settings")
        st.session_state.setdefault("steps", 75)
        st.session_state.setdefault("height", 512)
        st.session_state.setdefault("width", 512)
        st.session_state.setdefault("model_id", MODEL_CHOICES[0])

        st.session_state["model_id"] = st.selectbox("Model", MODEL_CHOICES, index=0)
        st.session_state["steps"] = st.slider("Steps", 1, 100, st.session_state["steps"])
        st.session_state["height"] = st.select_slider("Height", options=[256, 384, 448, 512, 576, 640, 768], value=st.session_state["height"])
        st.session_state["width"] = st.select_slider("Width", options=[256, 384, 448, 512, 576, 640, 768], value=st.session_state["width"])

        st.markdown("---")
        st.header("🗂️ Gallery Filter")
        view = st.radio("Show", ["My images", "All users"], index=0, horizontal=True)
        st.session_state["gallery_scope"] = view

# ----------------- MAIN PAGES --------------------
def run_generation(model_id: str, prompt: str, steps: int, h: int, w: int, n_images: int):
    pipe = get_pipeline(model_id)
    result = pipe([prompt] * n_images, num_inference_steps=steps, height=h, width=w)
    return result.images

def page_generate(username: str):
    st.title("🖼️ Generate Images")
    st.caption("Powered by Stable Diffusion on CPU.")

    with st.form("gen_form"):
        prompt = st.text_area("Prompt", value="", placeholder="Describe your image", height=100)
        n_images = st.slider("Number of images", 1, 4, 1)
        submitted = st.form_submit_button("Generate")
    if not submitted:
        return

    if not prompt.strip():
        st.warning("Please enter a prompt.")
        return

    steps = int(st.session_state.get("steps", 75))
    h = int(st.session_state.get("height", 512))
    w = int(st.session_state.get("width", 512))
    model_id = st.session_state.get("model_id", MODEL_CHOICES[0])

    with st.status("Submitting job…", expanded=True) as status:
        future = EXECUTOR.submit(run_generation, model_id, prompt.strip(), steps, h, w, n_images)
        st.write(f"Model: {model_id} | Steps: {steps} | Size: {w}×{h} | Images: {n_images}")
        images = future.result()
        status.update(label="Done", state="complete")

    saved_paths = []
    cols = st.columns(min(n_images, 4))
    for idx, img in enumerate(images):
        p = save_image(img, username, prompt)
        saved_paths.append(p)
        with cols[idx % len(cols)]:
            st.image(img, caption=p.name, width="stretch")
            st.download_button("Download", data=p.read_bytes(), file_name=p.name, mime="image/jpeg", width="stretch")

    st.success(f"Saved {len(saved_paths)} image(s) to {user_dir(username)}")

def page_gallery(username: str):
    st.title("🗃️ Gallery")

    scope = st.session_state.get("gallery_scope", "My images")
    if scope == "My images":
        paths = list_images(username)
    else:
        paths = list_images(None)

    if not paths:
        st.info("No images yet. Generate something on the **Generate** tab!")
        return

    cols_per_row = 4
    rows = (len(paths) + cols_per_row - 1) // cols_per_row
    for r in range(rows):
        cols = st.columns(cols_per_row)
        for c in range(cols_per_row):
            i = r * cols_per_row + c
            if i >= len(paths):
                break
            p = paths[i]
            with cols[c]:
                st.image(str(p), width="stretch", caption=f"{p.parent.name} / {p.name}")
                with st.expander("Details"):
                    st.code(str(p.resolve()))
                    st.button("Delete", key=f"del_{p.name}_{i}", on_click=lambda pp=p: (pp.unlink(missing_ok=True), st.rerun()))

# ----------------- APP ROUTER --------------------
def main():
    username = require_login()
    sidebar(username)

    tab_generate, tab_gallery = st.tabs(["✨ Generate", "🖼️ Gallery"])
    with tab_generate:
        page_generate(username)
    with tab_gallery:
        page_gallery(username)

if __name__ == "__main__":
    main()
