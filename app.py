
import re
import urllib.parse
import pandas as pd
import numpy as np
import streamlit as st

# Tenta capturar localização via navegador (se disponível)
try:
    from streamlit_js_eval import get_geolocation
    JS_EVAL_AVAILABLE = True
except Exception:
    JS_EVAL_AVAILABLE = False

st.set_page_config(page_title="Localizador de Unidades Consumidoras", page_icon="🗺️", layout="centered")
st.markdown("<h1 style='text-align:center;margin-bottom:0.2rem'>Localizador de Unidades Consumidoras</h1>", unsafe_allow_html=True)
st.caption("Busque por **Medidor** ou **UC**, visualize os dados e abra a localização no Google Maps. Complete coordenadas manualmente, por link ou via GPS.")

CSV_PATH = "dados_clientes.csv"
PRIMARY_KEYS = ["UC", "Medidor"]

def to_float_or_nan(x):
    try:
        return float(str(x).strip().replace(",", "."))
    except Exception:
        return np.nan

def parse_coordenadas(texto):
    texto = texto.strip()

    # Decimal simples
    match_decimal = re.match(r'(-?\d{1,2}\.\d+)[,\s]+(-?\d{1,3}\.\d+)', texto)
    if match_decimal:
        return float(match_decimal.group(1)), float(match_decimal.group(2))

    # Lat/Lon textual
    match_textual = re.search(r'(-?\d{1,2}\.\d+).*(\-?\d{1,3}\.\d+)', texto)
    if match_textual:
        return float(match_textual.group(1)), float(match_textual.group(2))

    # DMS (graus, minutos, segundos)
    dms_regex = re.compile(
        r'(\\d{1,3})[°º]\\s*(\\d{1,2})\'\\s*(\\d{1,2}(?:\\.\\d+)?)"?\\s*([NS]),?\\s*(\\d{1,3})[°º]\\s*(\\d{1,2})\'\\s*(\\d{1,2}(?:\\.\\d+)?)"?\\s*([EW])'
    )
    match_dms = dms_regex.search(texto)
    if match_dms:
        def dms_para_decimal(g,m,s,d):
            dec = float(g)+float(m)/60+float(s)/3600
            if d in ['S','W']: dec *= -1
            return round(dec,6)
        lat = dms_para_decimal(match_dms.group(1),match_dms.group(2),match_dms.group(3),match_dms.group(4))
        lon = dms_para_decimal(match_dms.group(5),match_dms.group(6),match_dms.group(7),match_dms.group(8))
        return lat, lon

    # Link do Google Maps
    link_match = re.search(r'(-?\\d{1,2}\\.\\d+)[,\\s]+(-?\\d{1,3}\\.\\d+)', texto)
    if link_match:
        return float(link_match.group(1)), float(link_match.group(2))

    return np.nan, np.nan

def google_maps_link(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return ""
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"

@st.cache_data(ttl=60)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    for c in ["Latitude","Longitude"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(",", ".", regex=False)
    return df

def save_data(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False, encoding="utf-8")

df = load_data(CSV_PATH)

cidades = sorted([c for c in df["Cidade"].dropna().unique().tolist() if c])
cidade = st.selectbox("Cidade", options=["(todas)"] + cidades, index=0)
query = st.text_input("Digite o número do **Medidor** ou da **UC**:")

df_f = df.copy()
if cidade != "(todas)":
    df_f = df_f[df_f["Cidade"].astype(str).str.lower() == cidade.lower()]

result = None
if query:
    q = query.strip()
    exact_medidor = df_f[df_f["Medidor"].astype(str) == q]
    exact_uc = df_f[df_f["UC"].astype(str) == q]
    if len(exact_medidor) == 1:
        result = exact_medidor.iloc[0]
    elif len(exact_uc) == 1:
        result = exact_uc.iloc[0]

if result is not None:
    medidor = str(result.get("Medidor", "") or "").strip()
    uc = str(result.get("UC", "") or "").strip()
    cliente = str(result.get("Cliente", "") or "").strip()
    cidade_r = str(result.get("Cidade", "") or "").strip()
    lat = to_float_or_nan(result.get("Latitude", ""))
    lon = to_float_or_nan(result.get("Longitude", ""))

    st.markdown(f"### {medidor} — {cliente}")
    st.text(f"UC: {uc} | Cidade: {cidade_r}")
    st.text(f"Coordenadas: {('%.6f' % lat if not np.isnan(lat) else '—')}, {('%.6f' % lon if not np.isnan(lon) else '—')}")

    if not np.isnan(lat) and not np.isnan(lon):
        st.link_button("🗺️ Abrir no Google Maps", google_maps_link(lat, lon), use_container_width=True)
    else:
        st.info("Sem coordenada registrada. Complete abaixo 👇")

    modo = st.radio("Modo:", ["📍 Capturar GPS", "✏️ Inserir manualmente"])

    if modo == "✏️ Inserir manualmente":
        texto_coord = st.text_input("Cole a coordenada (decimal, DMS ou link)")
        if st.button("Salvar coordenada (manual)"):
            lat_m, lon_m = parse_coordenadas(texto_coord)
            if np.isnan(lat_m) or np.isnan(lon_m):
                st.error("❌ Não consegui interpretar a coordenada.")
            else:
                idx = df[(df["Medidor"].astype(str) == medidor) | (df["UC"].astype(str) == uc)].index
                if len(idx):
                    df.loc[idx, "Latitude"] = f"{lat_m:.6f}"
                    df.loc[idx, "Longitude"] = f"{lon_m:.6f}"
                    save_data(df, CSV_PATH)
                    st.success("✅ Cliente atualizado com sucesso!")
                    st.map(pd.DataFrame({'lat':[lat_m],'lon':[lon_m]}))
