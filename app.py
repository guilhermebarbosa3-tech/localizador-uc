import streamlit as st
import re
from typing import Optional, List, Dict
from urllib.parse import unquote, quote_plus
from urllib.parse import urlparse
from datetime import datetime, timezone
from streamlit_js_eval import get_geolocation
from supabase import create_client

# =====================================
# CONFIGURAÇÕES INICIAIS
# =====================================
st.set_page_config(page_title="Localizador de Unidades Consumidoras", layout="centered")

st.title("📍 Localizador de Unidades Consumidoras")
st.caption("Consulte e atualize coordenadas geográficas de clientes pelo número do medidor ou da unidade consumidora.")

# =====================================
# SUPABASE CLIENTE
# =====================================
missing_secrets = [key for key in ("SUPABASE_URL", "SUPABASE_KEY") if key not in st.secrets]

if missing_secrets:
    st.error("Configuração do Supabase ausente no Streamlit Cloud.")
    st.info("Adicione `SUPABASE_URL` e `SUPABASE_KEY` em `Manage app` -> `Settings` -> `Secrets`.")
    st.stop()

supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]

supabase = create_client(
    supabase_url,
    supabase_key,
)
supabase_host = urlparse(supabase_url).netloc
st.caption(f"🔧 Diagnóstico temporário — Supabase ativo: {supabase_host}")

if "debug_cadastro" in st.session_state:
    with st.expander("🔧 Diagnóstico temporário do último cadastro", expanded=True):
        st.write("DEBUG — payload enviado:", st.session_state["debug_cadastro"].get("payload"))
        st.write("DEBUG — retorno do INSERT:", st.session_state["debug_cadastro"].get("retorno_insert"))
        st.write("DEBUG — confirmação após INSERT:", st.session_state["debug_cadastro"].get("confirmacao"))

        if st.button("Limpar diagnóstico temporário"):
            del st.session_state["debug_cadastro"]
            st.rerun()

TABELA = "unidades_consumidoras"

# =====================================
# FUNÇÕES AUXILIARES
# =====================================

def extrair_coordenadas(texto):
    """Extrai coordenadas (latitude, longitude) em decimal a partir de:
    - Texto/link contendo dois decimais (ex.: -22.123, -47.456)
    - Link do Google Maps com @lat,lon ou query=lat,lon
    - Também tenta DMS como fallback
    Retorna (lat, lon) como floats ou (None, None) se não conseguir.
    """
    if texto is None:
        return None, None
    s = unquote(str(texto)).strip()
    if not s:
        return None, None

    # 1) Decimais diretos (inclui muitos links do Google com @lat,lon)
    decimais = re.findall(r"-?\d+\.\d+", s)
    if len(decimais) >= 2:
        try:
            return float(decimais[0]), float(decimais[1])
        except Exception:
            pass

    # 2) Normaliza vírgula decimal para ponto
    s_norm = s.replace(',', '.')
    decimais2 = re.findall(r"-?\d+\.\d+", s_norm)
    if len(decimais2) >= 2:
        try:
            return float(decimais2[0]), float(decimais2[1])
        except Exception:
            pass

    # 3) DMS com hemisfério (N/S/E/W)
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

    # 4) DMS sem hemisfério (assume primeiro lat e segundo lon)
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

# =====================================
# INTEGRAÇÃO SUPABASE - FUNÇÕES
# =====================================

def listar_cidades() -> List[str]:
    try:
        cidades = set()
        tamanho_lote = 1000
        inicio = 0

        while True:
            fim = inicio + tamanho_lote - 1

            res = (
                supabase
                .table(TABELA)
                .select("cidade")
                .range(inicio, fim)
                .execute()
            )

            registros = res.data or []

            for registro in registros:
                cidade = str(registro.get("cidade", "")).strip()
                if cidade:
                    cidades.add(cidade)

            if len(registros) < tamanho_lote:
                break

            inicio += tamanho_lote

        return sorted(cidades)
    except Exception as e:
        st.error(f"Erro ao listar cidades: {e}")
        return []


def buscar_unidades(cidade: str, termo: str) -> List[Dict]:
    try:
        query = supabase.table(TABELA).select("*")
        if cidade and cidade != "Todas":
            query = query.eq("cidade", cidade)
        termo = (termo or "").strip()
        if termo:
            padrao = f"%{termo}%"
            query = query.or_(f"uc.ilike.{padrao},medidor.ilike.{padrao}")
        res = query.order("cliente").limit(100).execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro na busca: {e}")
        return []


def atualizar_coordenada(reg_id: int, latitude: float, longitude: float) -> bool:
    try:
        agora = datetime.now(timezone.utc).isoformat()
        supabase.table(TABELA).update({
            "latitude": latitude,
            "longitude": longitude,
            "atualizado_em": agora,
        }).eq("id", reg_id).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar coordenada: {e}")
        return False


def cadastrar_unidade_original(dados: Dict) -> bool:
    # Validação obrigatória
    obrigatorios = ["cidade", "uc", "cliente"]
    faltando = [c for c in obrigatorios if not str(dados.get(c, "")).strip()]
    if faltando:
        st.error("Preencha os campos obrigatórios: cidade, UC e cliente.")
        return False
    try:
        payload = {
            "cidade": dados.get("cidade").strip(),
            "uc": str(dados.get("uc", "")).strip(),
            "medidor": str(dados.get("medidor", "")).strip(),
            "cliente": dados.get("cliente").strip(),
            "endereco": str(dados.get("endereco", "")).strip(),
            "latitude": dados.get("latitude"),
            "longitude": dados.get("longitude"),
        }
        supabase.table(TABELA).insert(payload).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao cadastrar unidade: {e}")
        return False

# =====================================
# INTERFACE PRINCIPAL
# =====================================

def cadastrar_unidade(dados: Dict) -> bool:
    obrigatorios = ["cidade", "uc", "cliente"]
    faltando = [c for c in obrigatorios if not str(dados.get(c, "")).strip()]

    if faltando:
        st.error("Preencha os campos obrigatórios: cidade, UC e cliente.")
        return False

    try:
        payload = {
            "cidade": str(dados.get("cidade", "")).strip(),
            "uc": str(dados.get("uc", "")).strip(),
            "medidor": str(dados.get("medidor", "")).strip(),
            "cliente": str(dados.get("cliente", "")).strip(),
            "endereco": str(dados.get("endereco", "")).strip(),
            "latitude": dados.get("latitude"),
            "longitude": dados.get("longitude"),
        }

        st.session_state["debug_cadastro"] = {
            "payload": payload,
            "retorno_insert": None,
            "confirmacao": None,
        }

        st.write("DEBUG — payload enviado:", payload)

        resposta_insert = (
            supabase
            .table(TABELA)
            .insert(payload)
            .execute()
        )

        st.session_state["debug_cadastro"]["retorno_insert"] = resposta_insert.data

        st.write("DEBUG — retorno do INSERT:", resposta_insert.data)

        if not resposta_insert.data:
            st.error("O Supabase não confirmou a inserção do cliente.")
            return False

        registro_inserido = resposta_insert.data[0]
        registro_id = registro_inserido.get("id")

        if not registro_id:
            st.error("O INSERT retornou dados, mas não retornou o ID do registro.")
            return False

        resposta_confirmacao = (
            supabase
            .table(TABELA)
            .select("id,cidade,uc,medidor,cliente")
            .eq("id", registro_id)
            .execute()
        )

        st.session_state["debug_cadastro"]["confirmacao"] = resposta_confirmacao.data

        st.write("DEBUG — confirmação após INSERT:", resposta_confirmacao.data)

        if not resposta_confirmacao.data:
            st.error("O INSERT foi executado, mas a consulta de confirmação não encontrou o registro.")
            return False

        return True

    except Exception as e:
        st.error(f"Erro ao cadastrar unidade no Supabase: {e}")
        return False

# Seletor de cidades
st.subheader("🔹 Escolha a cidade")
lista_cidades = ["Todas"] + listar_cidades()
cidade = st.selectbox("Selecione a cidade", lista_cidades, index=0)

# Campo de busca com botão
st.subheader("🔎 Localizar cliente")
if "termo_pesquisa" not in st.session_state:
    st.session_state["termo_pesquisa"] = ""
if "resultados_pesquisa" not in st.session_state:
    st.session_state["resultados_pesquisa"] = []
if "pesquisa_realizada" not in st.session_state:
    st.session_state["pesquisa_realizada"] = False
if "cidade_pesquisa" not in st.session_state:
    st.session_state["cidade_pesquisa"] = "Todas"

with st.form("form_pesquisa"):
    termo_digitado = st.text_input(
        "Digite o número do medidor ou da unidade consumidora",
        value=st.session_state.get("termo_pesquisa", ""),
    )
    pesquisar = st.form_submit_button(
        "🔎 Pesquisar",
        use_container_width=True,
    )

if pesquisar:
    termo = termo_digitado.strip()

    if not termo:
        st.warning("Informe uma UC ou um número de medidor antes de pesquisar.")
    else:
        st.session_state["termo_pesquisa"] = termo
        st.session_state["resultados_pesquisa"] = buscar_unidades(cidade, termo)
        st.session_state["pesquisa_realizada"] = True
        st.session_state["cidade_pesquisa"] = cidade

# Filtro por status de localização
st.subheader("🔖 Status da localização")
opcoes_status = ["Todos", "Com coordenadas", "Sem dados"]
status_sel = st.selectbox("Filtrar por status", opcoes_status, index=0)

# =====================================
# RESULTADOS
# =====================================
resultado = st.session_state.get("resultados_pesquisa", [])
pesquisa_realizada = st.session_state.get("pesquisa_realizada", False)
cidade_pesquisa = st.session_state.get("cidade_pesquisa", cidade)

# Aplica filtro de status no cliente
def tem_coord(r):
    lat = r.get("latitude")
    lon = r.get("longitude")
    try:
        return lat is not None and lon is not None and str(lat).strip() != "" and str(lon).strip() != ""
    except Exception:
        return False

if status_sel == "Com coordenadas":
    resultado = [r for r in resultado if tem_coord(r)]
elif status_sel == "Sem dados":
    resultado = [r for r in resultado if not tem_coord(r)]

if resultado:
    for idx, row in enumerate(resultado):
        st.markdown("---")
        st.markdown(f"### 👤 {row.get('cliente','')}")
        st.markdown(f"**Medidor:** {row.get('medidor','')}  |  **UC:** {row.get('uc','')}")
        st.markdown(f"**Endereço:** {row.get('endereco','')}")
        st.markdown(f"**Cidade:** {row.get('cidade','')}")

        lat = row.get("latitude")
        lon = row.get("longitude")
        has_coord = lat not in (None, "") and lon not in (None, "")

        if has_coord:
            st.markdown("✅ Status: Com coordenadas")
            st.markdown(f"🌍 **Coordenada atual:** {lat}, {lon}")
            url_maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            st.link_button("🗺️ Abrir no Google Maps", url_maps, type="primary", use_container_width=True)

            # Editar coordenada existente
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
                        if atualizar_coordenada(row["id"], float(new_lat), float(new_lon)):
                            st.success("Coordenada atualizada com sucesso!")
                            st.rerun()
            else:
                coord_input_edit = st.text_input(
                    "Cole um link do Google Maps ou as coordenadas:",
                    key=f"manual_editar_{idx}"
                )
                if st.button("Salvar coordenada", key=f"salvar_editar_{idx}"):
                    new_lat, new_lon = extrair_coordenadas(coord_input_edit)
                    if new_lat is not None and new_lon is not None:
                        if atualizar_coordenada(row["id"], float(new_lat), float(new_lon)):
                            st.success("Coordenada atualizada com sucesso!")
                            st.rerun()
                    else:
                        st.error("Formato inválido. Informe coordenadas decimais (ex.: -22.3577,-47.3627) ou um link que contenha essas coordenadas.")
        else:
            st.markdown("⬜ Status: Sem dados")
            # Sugerir busca do endereço no Maps
            endereco_busca = f"{row.get('endereco','')} {row.get('cidade','')}".strip()
            if endereco_busca:
                url_maps_busca = f"https://www.google.com/maps/search/?api=1&query={quote_plus(endereco_busca)}"
                st.link_button("🔎 Buscar endereço no Google Maps", url_maps_busca, use_container_width=True)

            st.markdown("#### ➕ Inserir coordenada")
            opcao = st.radio("Escolha o método:", ["Capturar GPS do celular", "Inserir manualmente"], key=f"opcao_{idx}")

            if opcao == "Capturar GPS do celular":
                loc = get_geolocation()
                if loc:
                    lat_gps, lon_gps = loc["coords"]["latitude"], loc["coords"]["longitude"]
                    st.success(f"Coordenada detectada: ({lat_gps}, {lon_gps})")
                    if st.button("Salvar coordenada", key=f"gps_{idx}"):
                        if atualizar_coordenada(row["id"], float(lat_gps), float(lon_gps)):
                            st.success("Coordenada salva com sucesso!")
                            st.rerun()

            elif opcao == "Inserir manualmente":
                coord_input = st.text_input("Cole um link do Google Maps ou coordenada:", key=f"manual_{idx}")
                if st.button("Salvar coordenada", key=f"salvar_{idx}"):
                    lat_m, lon_m = extrair_coordenadas(coord_input)
                    if lat_m is not None and lon_m is not None:
                        if atualizar_coordenada(row["id"], float(lat_m), float(lon_m)):
                            st.success("Coordenada salva com sucesso!")
                            st.rerun()
                    else:
                        st.error("Formato inválido. Informe coordenadas decimais (ex.: -22.3577,-47.3627) ou um link que contenha essas coordenadas.")
else:
    if pesquisa_realizada:
        if cidade_pesquisa == "Todas":
            st.warning("Cliente não encontrado.")
        else:
            st.warning("Cliente não encontrado nesta cidade.")
        if st.button("Cadastrar novo cliente"):
            st.session_state["novo_cliente"] = st.session_state.get("termo_pesquisa", "")

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
    coord_livre = st.text_input("Coordenadas (link/decimal) - opcional")

    # Cidade
    if cidade == "Todas":
        cidades_disponiveis = listar_cidades()
        if cidades_disponiveis:
            cidade_novo = st.selectbox("Cidade do cliente", cidades_disponiveis)
        else:
            cidade_novo = st.text_input("Cidade do cliente")
    else:
        cidade_novo = cidade

    if st.button("Salvar novo cliente"):
        # Extrai coordenadas prioritariamente do campo livre
        lat_final, lon_final = None, None
        if coord_livre:
            lat_final, lon_final = extrair_coordenadas(coord_livre)
        if (lat_final is None or lon_final is None) and (nova_lat or nova_lon):
            try:
                lat_final = float(str(nova_lat).replace(',', '.')) if nova_lat else None
                lon_final = float(str(nova_lon).replace(',', '.')) if nova_lon else None
            except Exception:
                lat_final, lon_final = None, None

        ok = cadastrar_unidade({
            "cidade": cidade_novo,
            "uc": nova_uc,
            "medidor": novo_medidor,
            "cliente": novo_nome,
            "endereco": novo_endereco,
            "latitude": lat_final,
            "longitude": lon_final,
        })
        if ok:
            st.success("Cliente cadastrado com sucesso!")
            del st.session_state["novo_cliente"]
            st.rerun()
