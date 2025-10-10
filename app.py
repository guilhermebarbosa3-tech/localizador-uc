import streamlit as st
import pandas as pd
import re
import os
import math
from typing import Optional
from unidecode import unidecode
from urllib.parse import unquote, quote_plus
from streamlit_js_eval import get_geolocation

# =====================================
# CONFIGURAÇÕES INICIAIS
# =====================================
st.set_page_config(page_title="Localizador de Unidades Consumidoras", layout="centered")

st.title("📍 Localizador de Unidades Consumidoras")
st.caption("Consulte e atualize coordenadas geográficas de clientes pelo número do medidor ou da unidade consumidora.")

# =====================================
# FUNÇÕES AUXILIARES
# =====================================

def carregar_dados():
    """Carrega o arquivo CSV, criando um novo se não existir"""
    if not os.path.exists("dados_clientes.csv"):
        df_vazio = pd.DataFrame(columns=["Cidade", "UC", "Medidor", "Cliente", "Endereço", "Latitude", "Longitude"])
        df_vazio.to_csv("dados_clientes.csv", index=False, encoding="utf-8")
    return pd.read_csv("dados_clientes.csv", dtype=str)

def salvar_dados(df):
    """Salva os dados atualizados"""
    df.to_csv("dados_clientes.csv", index=False, encoding="utf-8")

def extrair_coordenadas(texto):
    """Extrai coordenadas (latitude, longitude) em decimal a partir de:
    - Link do Google Maps, contendo @lat,lon ou query=lat,lon
    - Decimais simples (ex.: -22.123, -47.456)
    - DMS (graus, minutos, segundos) com hemisférios (N S E W), ex.: 22°18'16.4"S 47°20'31.2"W
    Retorna (lat, lon) como floats ou (None, None) se não conseguir.
    """
    if texto is None:
        return None, None
    s = unquote(str(texto)).strip()
    if not s:
        return None, None

    # 1) Tenta extrair decimais diretos (inclui a maioria dos links com @lat,lon)
    decimais = re.findall(r"-?\d+\.\d+", s)
    if len(decimais) >= 2:
        try:
            return float(decimais[0]), float(decimais[1])
        except Exception:
            pass

    # 2) Tenta extrair via padrões de query do Google (quando há vírgula decimal com vírgula, etc.)
    # Ex.: query=-22,1234,-47,5678 (vamos normalizar vírgula para ponto)
    s_norm = s.replace(',', '.')
    decimais2 = re.findall(r"-?\d+\.\d+", s_norm)
    if len(decimais2) >= 2:
        try:
            return float(decimais2[0]), float(decimais2[1])
        except Exception:
            pass

    # 3) Tenta DMS com hemisfério (N/S/E/W)
    # Formatos aceitos: 22°18'16.4"S 47°20'31.2"W ou 22 18 16.4 S, 47 20 31.2 W
    dms_pattern = re.compile(
        r"(?P<deg>\d{1,3})[^0-9a-zA-Z]+(?P<min>\d{1,2})[^0-9a-zA-Z]+(?P<sec>\d{1,2}(?:[\.,]\d+)?)\s*([NnSsEeWw])"
    )

    def dms_to_decimal(deg, minute, sec, hemi):
        deg = float(deg)
        minute = float(minute)
        sec = float(str(sec).replace(',', '.'))
        val = deg + minute / 60.0 + sec / 3600.0
        hemi = str(hemi).upper()
        if hemi in ('S', 'W'):
            val = -val
        return val

    matches = list(dms_pattern.finditer(s))
    if len(matches) >= 2:
        # Identifica qual é lat (N/S) e qual é lon (E/W)
        lat_val, lon_val = None, None
        for m in matches:
            deg = m.group('deg'); minute = m.group('min'); sec = m.group('sec'); hemi = m.group(4)
            val = dms_to_decimal(deg, minute, sec, hemi)
            if str(hemi).upper() in ('N', 'S') and lat_val is None:
                lat_val = val
            elif str(hemi).upper() in ('E', 'W') and lon_val is None:
                lon_val = val
        if lat_val is not None and lon_val is not None:
            return lat_val, lon_val

    # 4) Tenta DMS sem hemisfério (assume primeiro como lat e segundo como lon, com sinais positivos)
    dms_no_hemi_pattern = re.compile(
        r"(?P<deg>\d{1,3})[^0-9a-zA-Z]+(?P<min>\d{1,2})[^0-9a-zA-Z]+(?P<sec>\d{1,2}(?:[\.,]\d+)?)"
    )
    matches2 = list(dms_no_hemi_pattern.finditer(s))
    if len(matches2) >= 2:
        try:
            d1 = matches2[0]; d2 = matches2[1]
            lat_val = dms_to_decimal(d1.group('deg'), d1.group('min'), d1.group('sec'), 'N')
            lon_val = dms_to_decimal(d2.group('deg'), d2.group('min'), d2.group('sec'), 'E')
            return lat_val, lon_val
        except Exception:
            pass

    return None, None

def extrair_link_maps(texto: str) -> Optional[str]:
    """Retorna a URL se o texto parecer um link do Google Maps (inclui encurtadores maps.app.goo.gl).
    Caso contrário, retorna None.
    """
    if not texto:
        return None
    s = str(texto).strip()
    # Aceita formatos comuns de links do Google Maps
    padrao = re.compile(r"^(https?://)?(maps\.app\.goo\.gl|goo\.gl/maps|www\.google\.com/maps|maps\.google\.com|google\.com/maps)[^\s]*", re.IGNORECASE)
    m = padrao.match(s)
    if m:
        # Garante que tenha esquema http/https
        if not s.lower().startswith(("http://", "https://")):
            s = "https://" + s
        return s
    return None

# =====================================
# INTERFACE PRINCIPAL
# =====================================
df = carregar_dados()

# Padroniza e mapeia nomes de colunas do CSV para o padrão esperado
def _norm_col(s: str) -> str:
    s = unidecode(str(s)).lower().strip()
    # Mantém apenas letras, números e espaços
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

df.columns = [str(c).strip() for c in df.columns]

# Mapeamento exato por nome normalizado
map_exato = {
    "unidade consumidora": "UC",
    "uc numero": "UC",
    "uc": "UC",
    "numero do medidor": "Medidor",
    "medidor": "Medidor",
    "equipamento": "Medidor",
    "cidade": "Cidade",
    "descricao da localidade": "Cidade",
    "localidade": "Cidade",
    "nome do cliente": "Cliente",
    "cliente": "Cliente",
    "endereco": "Endereço",
    "latitude": "Latitude",
    "valor latitude": "Latitude",
    "longitude": "Longitude",
    "valor longitude": "Longitude",
    "link": "Link",
}

# Heurísticas por conteúdo (contém palavras)
def _heuristica(norm: str) -> Optional[str]:
    if "latitude" in norm:
        return "Latitude"
    if "longitude" in norm:
        return "Longitude"
    if ("unidade" in norm and "consumidora" in norm) or norm == "uc":
        return "UC"
    if ("medidor" in norm) or ("equipamento" in norm):
        return "Medidor"
    if "localidade" in norm or "cidade" in norm:
        return "Cidade"
    if ("nome" in norm and "cliente" in norm) or norm == "cliente":
        return "Cliente"
    if "endereco" in norm:
        return "Endereço"
    return None

rename_map = {}
alvos_existentes = set(df.columns)
for col in list(df.columns):
    norm = _norm_col(col)
    alvo = map_exato.get(norm)
    if not alvo:
        alvo = _heuristica(norm)
    if alvo and alvo not in alvos_existentes:
        rename_map[col] = alvo
        alvos_existentes.add(alvo)

if rename_map:
    df.rename(columns=rename_map, inplace=True)

# Garante colunas obrigatórias
colunas_obrigatorias = ["Cidade", "UC", "Medidor", "Cliente", "Endereço", "Latitude", "Longitude", "Link"]
for col in colunas_obrigatorias:
    if col not in df.columns:
        df[col] = ""

# Seletor de cidades e campo de busca exibidos diretamente (sem expander).
# Inclui a opção "Todas" como a primeira opção no seletor de cidades.
# Opções de cidades dinâmicas a partir do CSV
cidades_existentes = []
if not df.empty and "Cidade" in df.columns:
    cidades_existentes = sorted([
        str(c).strip() for c in df["Cidade"].dropna().unique().tolist() if str(c).strip() != ""
    ])

opcoes_cidade = ["Todas"] + cidades_existentes

st.subheader("🔹 Escolha a cidade")
cidade = st.selectbox("Selecione a cidade", opcoes_cidade, index=0)

# Campo de busca automática
st.subheader("🔎 Localizar cliente")

# Estado da busca para melhor UX no mobile: campo de entrada e valor efetivamente pesquisado
if "busca_input" not in st.session_state:
    st.session_state["busca_input"] = ""
if "busca_ativa" not in st.session_state:
    st.session_state["busca_ativa"] = ""

st.session_state["busca_input"] = st.text_input(
    "Digite o número do medidor ou da unidade consumidora",
    value=st.session_state.get("busca_input", ""),
    key="busca_box"
)

cols_busca = st.columns(2)
with cols_busca[0]:
    pesquisar_clicked = st.button("Pesquisar", type="primary", use_container_width=True)
with cols_busca[1]:
    limpar_clicked = st.button("Limpar", use_container_width=True)

if pesquisar_clicked:
    st.session_state["busca_ativa"] = str(st.session_state.get("busca_input", "")).strip()
    # Rerun para refletir a pesquisa
    st.rerun()

if limpar_clicked:
    st.session_state["busca_input"] = ""
    st.session_state["busca_ativa"] = ""
    st.rerun()

busca_text = st.session_state.get("busca_ativa", "").strip()

# Filtro por status de localização
st.subheader("🔖 Status da localização")
opcoes_status = ["Todos", "Com coordenadas", "Com link apenas", "Sem dados"]
status_sel = st.selectbox("Filtrar por status", opcoes_status, index=0)

# =====================================
# RESULTADO DA BUSCA
# =====================================
resultado = pd.DataFrame()

if busca_text:
    # Se "Todas" for selecionada, não filtra por cidade
    if cidade == "Todas":
        filtro_cidade = pd.Series([True] * len(df))
    else:
        filtro_cidade = (df["Cidade"] == cidade)

    filtro_busca = (
        df["UC"].astype(str).str.contains(busca_text, case=False, na=False) |
        df["Medidor"].astype(str).str.contains(busca_text, case=False, na=False)
    )

    base = df[filtro_cidade & filtro_busca].copy()

    # Aplica filtro de status
    has_lat = base["Latitude"].astype(str).str.strip() != ""
    has_lon = base["Longitude"].astype(str).str.strip() != ""
    has_coord = has_lat & has_lon
    has_link = base["Link"].astype(str).str.strip() != ""

    if status_sel == "Com coordenadas":
        resultado = base[has_coord]
    elif status_sel == "Com link apenas":
        resultado = base[has_link & (~has_coord)]
    elif status_sel == "Sem dados":
        resultado = base[(~has_link) & (~has_coord)]
    else:
        resultado = base

if not resultado.empty:
    for idx, row in resultado.iterrows():
        st.markdown("---")
        st.markdown(f"### 👤 {row['Cliente']}")
        st.markdown(f"**Medidor:** {row['Medidor']}  |  **UC:** {row['UC']}")
        st.markdown(f"**Endereço:** {row['Endereço']}")
        st.markdown(f"**Cidade:** {row['Cidade']}")

        # Badge de status
        has_lat = str(row.get("Latitude", "")).strip() != ""
        has_lon = str(row.get("Longitude", "")).strip() != ""
        has_coord = has_lat and has_lon
        has_link = isinstance(row.get("Link", ""), str) and row.get("Link", "").strip() != ""
        if has_coord:
            st.markdown("✅ Status: Com coordenadas")
        elif has_link:
            st.markdown("🔗 Status: Com link apenas")
        else:
            st.markdown("⬜ Status: Sem dados")

        lat, lon = row.get("Latitude"), row.get("Longitude")
        if pd.notna(lat) and pd.notna(lon) and not (str(lat).strip() == "" or str(lon).strip() == ""):
            st.markdown(f"🌍 **Coordenada atual:** {lat}, {lon}")
            url_maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            st.link_button("🗺️ Abrir no Google Maps", url_maps, type="primary", use_container_width=True)

            # Se houver um link salvo, exibe também o botão para abrir
            link_salvo_existente = row.get("Link")
            if isinstance(link_salvo_existente, str) and link_salvo_existente.strip() != "":
                st.link_button("🗺️ Abrir link Google Maps (salvo)", link_salvo_existente.strip(), use_container_width=True)

            # Seção para editar coordenada existente
            st.markdown("#### ✏️ Editar coordenada")
            opcao_editar = st.radio(
                "Escolha o método:",
                ["Capturar GPS do dispositivo", "Inserir manualmente"],
                key=f"opcao_editar_{idx}"
            )

            if opcao_editar == "Capturar GPS do dispositivo":
                loc = get_geolocation()
                if loc:
                    new_lat, new_lon = loc["coords"]["latitude"], loc["coords"]["longitude"]
                    st.success(f"Coordenada detectada: ({new_lat}, {new_lon})")
                    if st.button("Salvar coordenada", key=f"gps_editar_{idx}"):
                        df.loc[df["UC"] == row["UC"], ["Latitude", "Longitude", "Link"]] = [new_lat, new_lon, ""]
                        salvar_dados(df)
                        st.success("Coordenada atualizada com sucesso!")
                        st.rerun()
            else:
                coord_input_edit = st.text_input(
                    "Cole o link do Google Maps ou coordenada:",
                    key=f"manual_editar_{idx}"
                )
                if st.button("Salvar coordenada", key=f"salvar_editar_{idx}"):
                    # Prioriza tratar como LINK quando a UC ja possui coordenadas
                    link_novo = extrair_link_maps(coord_input_edit)
                    if link_novo:
                        # Limpa coordenadas para evitar confusão e salva apenas o link
                        df.loc[df["UC"] == row["UC"], ["Latitude", "Longitude", "Link"]] = ["", "", link_novo]
                        salvar_dados(df)
                        st.success("Link salvo e coordenadas anteriores apagadas.")
                        st.rerun()
                    else:
                        # Tenta interpretar como coordenadas (decimal ou DMS)
                        new_lat, new_lon = extrair_coordenadas(coord_input_edit)
                        if new_lat is not None and new_lon is not None:
                            df.loc[df["UC"] == row["UC"], ["Latitude", "Longitude", "Link"]] = [new_lat, new_lon, ""]
                            salvar_dados(df)
                            st.success("Coordenada atualizada com sucesso!")
                            st.rerun()
                        else:
                            st.error("Formato inválido. Insira um link do Google Maps ou coordenadas (decimal/DMS) válidas.")
        else:
            # Sem coordenadas numericas; checa se ha link salvo para ajustar a mensagem
            link_salvo = row.get("Link")
            if isinstance(link_salvo, str) and link_salvo.strip() != "":
                st.info("ℹ️ Sem coordenadas numéricas cadastradas. Há um link do Google Maps salvo.")
                st.link_button("🗺️ Abrir no Google Maps (link salvo)", link_salvo.strip(), type="primary", use_container_width=True)
            else:
                st.warning("⚠️ Sem localização cadastrada. Informe coordenadas ou salve um link do Google Maps.")
                # Botão para pesquisar pelo endereço no Google Maps
                endereco_busca = f"{row['Endereço']} {row['Cidade']}".strip()
                if endereco_busca and endereco_busca != "":
                    url_maps_busca = f"https://www.google.com/maps/search/?api=1&query={quote_plus(endereco_busca)}"
                    st.link_button("🔎 Buscar endereço no Google Maps", url_maps_busca, use_container_width=True)

            st.markdown("#### ➕ Inserir coordenada")
            opcao = st.radio("Escolha o método:", ["Capturar GPS do celular", "Inserir manualmente"], key=f"opcao_{idx}")

            if opcao == "Capturar GPS do celular":
                loc = get_geolocation()
                if loc:
                    lat, lon = loc["coords"]["latitude"], loc["coords"]["longitude"]
                    st.success(f"Coordenada detectada: ({lat}, {lon})")
                    if st.button("Salvar coordenada", key=f"gps_{idx}"):
                        df.loc[df["UC"] == row["UC"], ["Latitude", "Longitude"]] = [lat, lon]
                        salvar_dados(df)
                        st.success("Coordenada salva com sucesso!")
                        st.rerun()

            elif opcao == "Inserir manualmente":
                coord_input = st.text_input("Cole o link do Google Maps ou coordenada:", key=f"manual_{idx}")
                if st.button("Salvar coordenada", key=f"salvar_{idx}"):
                    lat, lon = extrair_coordenadas(coord_input)
                    if lat is not None and lon is not None:
                        df.loc[df["UC"] == row["UC"], ["Latitude", "Longitude", "Link"]] = [lat, lon, ""]
                        salvar_dados(df)
                        st.success("Coordenada salva com sucesso!")
                        st.rerun()
                    else:
                        # Se não extraiu coordenadas, tenta salvar o link
                        link = extrair_link_maps(coord_input)
                        if link:
                            df.loc[df["UC"] == row["UC"], ["Link"]] = [link]
                            salvar_dados(df)
                            st.success("Link salvo com sucesso!")
                            st.rerun()
                        else:
                            st.error("Formato inválido. Insira coordenadas ou um link válido do Google Maps.")
else:
    if busca_text != "":
        if cidade == "Todas":
            st.warning("Cliente não encontrado.")
        else:
            st.warning("Cliente não encontrado nesta cidade.")
        if st.button("Cadastrar novo cliente"):
            st.session_state["novo_cliente"] = busca_text

# =====================================
# CADASTRO DE NOVO CLIENTE
# =====================================
if "novo_cliente" in st.session_state:
    st.subheader("➕ Cadastrar novo cliente")

    nova_uc = st.text_input("Unidade Consumidora (UC)", value=st.session_state["novo_cliente"])
    novo_medidor = st.text_input("Número do Medidor")
    novo_nome = st.text_input("Nome do cliente")
    novo_endereco = st.text_input("Endereço")
    nova_lat = st.text_input("Latitude (opcional)")
    nova_lon = st.text_input("Longitude (opcional)")
    coord_livre = st.text_input("Coordenadas (link do Google / DMS / decimal) - opcional")
    link_informado = st.text_input("Link do Google Maps (opcional)")

    # Se "Todas" estiver selecionada, pedir a cidade do novo cliente
    if cidade == "Todas":
        if cidades_existentes:
            cidade_novo = st.selectbox("Cidade do cliente", cidades_existentes)
        else:
            cidade_novo = st.text_input("Cidade do cliente")
    else:
        cidade_novo = cidade

    if st.button("Salvar novo cliente"):
        # Precedência: coord_livre > (nova_lat, nova_lon)
        lat_final, lon_final = None, None
        if coord_livre:
            lat_final, lon_final = extrair_coordenadas(coord_livre)
        # Se não conseguiu por coord_livre, tenta lat/lon digitadas diretamente
        if (lat_final is None or lon_final is None) and (nova_lat or nova_lon):
            try:
                lat_final = float(str(nova_lat).replace(',', '.')) if nova_lat else None
                lon_final = float(str(nova_lon).replace(',', '.')) if nova_lon else None
            except Exception:
                lat_final, lon_final = None, None

        # Determina link a salvar
        link_final = ""
        if not (lat_final is not None and lon_final is not None):
            # Se não há coords extraídas, e coord_livre for um link válido, salva-o
            possivel_link = extrair_link_maps(coord_livre)
            if possivel_link:
                link_final = possivel_link
        # Se usuário forneceu explicitamente um link, prioriza
        if link_informado:
            possivel_link2 = extrair_link_maps(link_informado)
            if possivel_link2:
                link_final = possivel_link2

        novo = {
            "Cidade": cidade_novo,
            "UC": nova_uc,
            "Medidor": novo_medidor,
            "Cliente": novo_nome,
            "Endereço": novo_endereco,
            "Latitude": lat_final if lat_final is not None else (nova_lat or ""),
            "Longitude": lon_final if lon_final is not None else (nova_lon or ""),
            "Link": link_final
        }
        df = pd.concat([df, pd.DataFrame([novo])], ignore_index=True)
        salvar_dados(df)
        st.success(f"Cliente '{novo_nome}' cadastrado com sucesso!")
        del st.session_state["novo_cliente"]

# Exportação desativada conforme solicitação do usuário.
