
import re
import urllib.parse
import pandas as pd
import numpy as np
import streamlit as st

# Optional: get geolocation via browser (requires permissions)
try:
    from streamlit_js_eval import get_geolocation
    JS_EVAL_AVAILABLE = True
except Exception:
    JS_EVAL_AVAILABLE = False

st.set_page_config(page_title="Localizador de Unidades Consumidoras", page_icon="🗺️", layout="centered")

st.markdown("<h1 style='text-align:center;margin-bottom:0.2rem'>Localizador de Unidades Consumidoras</h1>", unsafe_allow_html=True)
st.caption("Busque por **Medidor** ou **UC**, visualize os dados e abra a localização no Google Maps. Complete coordenadas manualmente, por link ou via GPS.")

# ---------- Configurações principais ----------

CSV_PATH = "dados_clientes.csv"  # arquivo no mesmo diretório do app
PRIMARY_KEYS = ["UC", "Medidor"]  # chaves usadas para identificar registros

# Mapeamento flexível de nomes de colunas (planilhas diferentes)
COLUMN_ALIASES = {
    "Cidade": ["Cidade", "cidade", "descrição da localidade", "descricao da localidade", "localidade", "município", "municipio"],
    "UC": ["UC", "unidade consumidora", "unidade Consumidora", "unidade_consumidora", "unidade"],
    "Medidor": ["Medidor", "medidor", "equipamento", "nº medidor", "numero do medidor", "nº do medidor"],
    "Cliente": ["Cliente", "cliente", "nome do cliente", "nome", "titular"],
    "Endereço": ["Endereço", "endereco", "endereço"],
    "Latitude": ["Latitude", "latitude", "valor latitude", "lat"],
    "Longitude": ["Longitude", "longitude", "valor longitude", "lon", "long"],
}

def normalize_col(s: str) -> str:
    return str(s).strip().lower()

def find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols_norm = {normalize_col(c): c for c in df.columns}
    for alias in aliases:
        key = normalize_col(alias)
        if key in cols_norm:
            return cols_norm[key]
    # fallback: try contains
    for alias in aliases:
        key = normalize_col(alias)
        for c in df.columns:
            if key in normalize_col(c):
                return c
    return None

@st.cache_data(ttl=60)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    # Trim spaces
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    # Build a consistent schema
    colmap = {}
    for std_col, aliases in COLUMN_ALIASES.items():
        col = find_column(df, aliases)
        if col is None:
            # Create empty if not found
            df[std_col] = np.nan
            colmap[std_col] = std_col
        else:
            colmap[std_col] = col

    # Rename to standard names (without losing originals)
    df_std = df.rename(columns={colmap["Cidade"]:"Cidade",
                                colmap["UC"]:"UC",
                                colmap["Medidor"]:"Medidor",
                                colmap["Cliente"]:"Cliente",
                                colmap["Endereço"]:"Endereço",
                                colmap["Latitude"]:"Latitude",
                                colmap["Longitude"]:"Longitude"}, errors="ignore")

    # Ensure columns exist
    for c in ["Cidade","UC","Medidor","Cliente","Endereço","Latitude","Longitude"]:
        if c not in df_std.columns:
            df_std[c] = np.nan

    # Normalize decimal separators
    for c in ["Latitude","Longitude"]:
        df_std[c] = df_std[c].astype(str).str.replace(",", ".", regex=False)

    return df_std

def save_data(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False, encoding="utf-8")

def to_float_or_nan(x):
    try:
        return float(str(x).strip().replace(",", "."))
    except Exception:
        return np.nan

def parse_coords_from_text(s: str):
    """Accepts various formats:
    - Decimal: -22.3577, -47.3627  (comma or dot)
    - Google Maps URL: https://www.google.com/maps?q=-22.3577,-47.3627 or .../@-22.3577,-47.3627,18z
    - DMS: 22°22'18.5"S 47°25'01.2"W
    Returns (lat, lon) floats or (np.nan, np.nan) if not parsed.
    """
    if not s:
        return np.nan, np.nan
    text = s.strip()

    # Try URL patterns
    try:
        if text.startswith("http"):
            parsed = urllib.parse.urlparse(text)
            q = urllib.parse.parse_qs(parsed.query)
            if "q" in q:
                pair = q["q"][0]
                latlon = pair.replace(" ", "").replace("，", ",").replace(";", ",")
                parts = latlon.split(",")
                if len(parts) >= 2:
                    return to_float_or_nan(parts[0]), to_float_or_nan(parts[1])
            # Try /@lat,lon,
            m = re.search(r"/@(-?\d+\.?\d*),(-?\d+\.?\d*)", text)
            if m:
                return to_float_or_nan(m.group(1)), to_float_or_nan(m.group(2))
    except Exception:
        pass

    # Try plain decimal "lat, lon"
    if "," in text and ";" not in text and "°" not in text:
        parts = [p.strip() for p in text.replace("，", ",").split(",")]
        if len(parts) >= 2:
            lat = to_float_or_nan(parts[0])
            lon = to_float_or_nan(parts[1])
            if not np.isnan(lat) and not np.isnan(lon):
                return lat, lon

    # Try DMS (degrees/minutes/seconds)
    dms_regex = r"""(?xi)
        (?P<lat_deg>-?\d{1,3})[°\s]+(?P<lat_min>\d{1,2})['\s]+(?P<lat_sec>\d{1,2}(\.\d+)?)["]?\s*(?P<lat_dir>[NS])[,;\s]+
        (?P<lon_deg>-?\d{1,3})[°\s]+(?P<lon_min>\d{1,2})['\s]+(?P<lon_sec>\d{1,2}(\.\d+)?)["]?\s*(?P<lon_dir>[EWLO])
    """
    m = re.search(dms_regex, text)
    if m:
        def dms_to_dd(deg, min_, sec, dir_):
            deg = float(deg); min_ = float(min_); sec = float(sec)
            val = deg + min_/60 + sec/3600
            if dir_.upper() in ("S","W","O","L"):  # O/L for Oeste in PT
                val = -val
            return val
        lat = dms_to_dd(m.group("lat_deg"), m.group("lat_min"), m.group("lat_sec"), m.group("lat_dir"))
        lon = dms_to_dd(m.group("lon_deg"), m.group("lon_min"), m.group("lon_sec"), m.group("lon_dir"))
        return lat, lon

    return np.nan, np.nan

def google_maps_link(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return ""
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"

# ---------- Carrega dados ----------

df = load_data(CSV_PATH)

# Opções de cidades disponíveis
cidades = sorted([c for c in df["Cidade"].dropna().unique().tolist() if c])
cidade = st.selectbox("Cidade", options=["(todas)"] + cidades, index=0)

# Entrada de busca (sem botão)
query = st.text_input("Digite o número do **Medidor** ou da **UC**:")

# Filtragem por cidade
df_f = df.copy()
if cidade != "(todas)":
    df_f = df_f[df_f["Cidade"].astype(str).str.lower() == cidade.lower()]

# Lógica de busca
result = None
if query:
    q = query.strip()
    # Primeiro tenta match exato por Medidor e UC
    exact_medidor = df_f[df_f["Medidor"].astype(str) == q]
    exact_uc = df_f[df_f["UC"].astype(str) == q]
    if len(exact_medidor) == 1:
        result = exact_medidor.iloc[0]
    elif len(exact_uc) == 1:
        result = exact_uc.iloc[0]
    else:
        # Fallback: contém
        contains = df_f[(df_f["Medidor"].astype(str).str.contains(re.escape(q), case=False, na=False)) |
                        (df_f["UC"].astype(str).str.contains(re.escape(q), case=False, na=False))]
        if len(contains) == 1:
            result = contains.iloc[0]
        elif len(contains) > 1:
            st.info(f"Foram encontrados {len(contains)} resultados. Refine sua busca.")
            st.dataframe(contains[["Cidade","Cliente","Medidor","UC","Latitude","Longitude"]].reset_index(drop=True))
        else:
            st.warning("Nenhum cliente encontrado. Você pode cadastrar um **novo cliente** abaixo.")

# ---------- Exibição do resultado único ----------
if result is not None:
    st.divider()
    st.markdown("#### Resultado")

    # Destaques: Medidor (maior), UC e Cliente (médio)
    medidor = str(result.get("Medidor", "") or "").strip()
    uc = str(result.get("UC", "") or "").strip()
    cliente = str(result.get("Cliente", "") or "").strip()
    endereco = str(result.get("Endereço", "") or "").strip()
    cidade_r = str(result.get("Cidade", "") or "").strip()
    lat = to_float_or_nan(result.get("Latitude", ""))
    lon = to_float_or_nan(result.get("Longitude", ""))

    st.markdown(f"<div style='font-size:2rem;font-weight:800;line-height:1'>{medidor or '—'}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:1.3rem;font-weight:700;color:#555'>UC: {uc or '—'}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:1.1rem;font-weight:600;color:#777'>{cliente or '—'}</div>", unsafe_allow_html=True)
    st.text(f"Endereço: {endereco or '—'}")
    st.text(f"Cidade: {cidade_r or '—'}")
    st.text(f"Coordenadas: {('%.6f' % lat if not np.isnan(lat) else '—')}, {('%.6f' % lon if not np.isnan(lon) else '—')}")

    # Abrir no Google Maps
    if not np.isnan(lat) and not np.isnan(lon):
        st.link_button("🗺️ Abrir no Google Maps", google_maps_link(lat, lon), use_container_width=True)
    else:
        st.info("Sem coordenada registrada. Complete abaixo 👇")

    # ---- Completar coordenadas ----
    st.subheader("Completar/Atualizar coordenadas")

    tabs = st.tabs(["📍 Capturar GPS", "✏️ Inserir manualmente"])

    with tabs[0]:
        if JS_EVAL_AVAILABLE:
            loc = get_geolocation()
            if loc and isinstance(loc, dict) and loc.get("coords"):
                lat_gps = loc["coords"]["latitude"]
                lon_gps = loc["coords"]["longitude"]
                st.success(f"Localização capturada: {lat_gps:.6f}, {lon_gps:.6f}")
                if st.button("Salvar coordenada (GPS)"):
                    # Atualiza no df
                    idx = df[(df["Medidor"].astype(str) == medidor) | (df["UC"].astype(str) == uc)].index
                    if len(idx):
                        df.loc[idx, "Latitude"] = f"{lat_gps:.6f}"
                        df.loc[idx, "Longitude"] = f"{lon_gps:.6f}"
                        save_data(df, CSV_PATH)
                        st.success("Coordenada salva com sucesso! Recarregue a página para ver a atualização.")
            else:
                st.warning("Clique para permitir o GPS do navegador (se solicitado) e aguarde alguns segundos.")
        else:
            st.warning("Captura de GPS indisponível. Instale o pacote `streamlit-js-eval`.")

    with tabs[1]:
        manual = st.text_input("Cole aqui a coordenada (ex.: `-22.3577,-47.3627`, link do Google Maps ou DMS)")
        if st.button("Salvar coordenada (manual)"):
            lat_m, lon_m = parse_coords_from_text(manual)
            if np.isnan(lat_m) or np.isnan(lon_m):
                st.error("Não consegui interpretar a coordenada. Verifique o formato e tente novamente.")
            else:
                idx = df[(df["Medidor"].astype(str) == medidor) | (df["UC"].astype(str) == uc)].index
                if len(idx):
                    df.loc[idx, "Latitude"] = f"{lat_m:.6f}"
                    df.loc[idx, "Longitude"] = f"{lon_m:.6f}"
                    save_data(df, CSV_PATH)
                    st.success("Coordenada salva com sucesso! Recarregue a página para ver a atualização.")

st.divider()
st.subheader("➕ Cadastrar novo cliente")
with st.form("novo_cliente"):
    col1, col2 = st.columns(2)
    with col1:
        cidade_new = st.selectbox("Cidade", options=sorted([c for c in df["Cidade"].dropna().unique().tolist() if c] + ["Araras","Cordeirópolis","Leme"]), index=0)
        cliente_new = st.text_input("Nome do cliente")
        endereco_new = st.text_input("Endereço")
    with col2:
        uc_new = st.text_input("UC")
        medidor_new = st.text_input("Medidor")
        coord_new = st.text_input("Coordenada (opcional) — cole `lat,lon` ou link")

    submitted = st.form_submit_button("Salvar novo cliente")
    if submitted:
        lat_new, lon_new = parse_coords_from_text(coord_new) if coord_new.strip() else (np.nan, np.nan)
        # Evitar duplicidade por UC/Medidor
        dup = df[(df["UC"].astype(str) == uc_new.strip()) | (df["Medidor"].astype(str) == medidor_new.strip())]
        if len(dup) > 0:
            st.error("Já existe um registro com esta UC ou Medidor. Verifique antes de salvar.")
        else:
            new_row = {
                "Cidade": cidade_new.strip(),
                "UC": uc_new.strip(),
                "Medidor": medidor_new.strip(),
                "Cliente": cliente_new.strip(),
                "Endereço": endereco_new.strip(),
                "Latitude": (f"{lat_new:.6f}" if not np.isnan(lat_new) else ""),
                "Longitude": (f"{lon_new:.6f}" if not np.isnan(lon_new) else ""),
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_data(df, CSV_PATH)
            st.success("Novo cliente cadastrado com sucesso!")

st.divider()
st.caption("Arquivo de dados: `dados_clientes.csv`. As alterações são salvas neste arquivo em tempo real.")
