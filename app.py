import streamlit as st
import re
from typing import Optional, List, Dict
from urllib.parse import unquote, quote_plus
from datetime import datetime, timezone
from streamlit_js_eval import get_geolocation
from supabase import create_client

# =====================================
# CONFIGURAÇÕES INICIAIS
# =====================================
st.set_page_config(page_title="Localizador de UCs", layout="centered")

st.html("""<style>
  .block-container { padding-top: 0.8rem !important; padding-bottom: 2rem !important; }
  h1 { font-size: 1.5rem !important; }
  h2, h3 { font-size: 1.05rem !important; margin-top: 0.4rem !important; margin-bottom: 0.2rem !important; }
  .stRadio label { font-size: 0.9rem; }
  .stButton > button { border-radius: 8px; }
</style>""")

st.title("📍 Localizador de UCs")

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


def eh_url_maps(texto: str) -> bool:
    if not texto:
        return False

    s = str(texto).strip()
    padrao = re.compile(
        r"^https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.com(?:\.br)?/maps|maps\.google\.com(?:\.br)?)(?:[/?#].*)?$",
        re.IGNORECASE,
    )
    return bool(padrao.match(s))


def montar_url_maps(latitude=None, longitude=None, link_maps=None):
    link = str(link_maps).strip() if link_maps is not None else ""
    if link:
        return link

    lat = str(latitude).strip() if latitude is not None else ""
    lon = str(longitude).strip() if longitude is not None else ""
    if lat and lon:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    return None


def resolver_localizacao_manual(texto: str):
    mensagem_erro = (
        "Não foi possível interpretar a localização. Informe coordenadas válidas ou cole um link do Google Maps."
    )

    s = str(texto or "").strip()
    if not s:
        return {
            "latitude": None,
            "longitude": None,
            "link_maps": None,
            "erro": mensagem_erro,
        }

    if eh_url_maps(s):
        lat, lon = extrair_coordenadas(s)
        return {
            "latitude": lat,
            "longitude": lon,
            "link_maps": s,
            "erro": None,
        }

    lat, lon = extrair_coordenadas(s)
    if lat is None or lon is None:
        return {
            "latitude": None,
            "longitude": None,
            "link_maps": None,
            "erro": mensagem_erro,
        }

    return {
        "latitude": lat,
        "longitude": lon,
        "link_maps": None,
        "erro": None,
    }

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
    return atualizar_localizacao(reg_id, latitude=latitude, longitude=longitude, link_maps=None)


def atualizar_localizacao(
    reg_id: int,
    latitude=None,
    longitude=None,
    link_maps=None,
) -> bool:
    try:
        agora = datetime.now(timezone.utc).isoformat()
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "link_maps": str(link_maps).strip() if link_maps else None,
            "atualizado_em": agora,
        }
        supabase.table(TABELA).update(payload).eq("id", reg_id).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar localização: {e}")
        return False


def atualizar_resultado_em_sessao(reg_id, latitude=None, longitude=None, link_maps=None):
    resultados = st.session_state.get("resultados_pesquisa", [])
    for registro in resultados:
        if registro.get("id") == reg_id:
            registro["latitude"] = latitude
            registro["longitude"] = longitude
            registro["link_maps"] = str(link_maps).strip() if link_maps else None
            registro["atualizado_em"] = datetime.now(timezone.utc).isoformat()
            break
    st.session_state["resultados_pesquisa"] = resultados


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
            "link_maps": str(dados.get("link_maps", "")).strip() or None,
        }

        resposta_insert = (
            supabase
            .table(TABELA)
            .insert(payload)
            .execute()
        )

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
            .select("id,cidade,uc,medidor,cliente,latitude,longitude,link_maps")
            .eq("id", registro_id)
            .execute()
        )

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
if "termo_pesquisa_input" not in st.session_state:
    st.session_state["termo_pesquisa_input"] = st.session_state["termo_pesquisa"]
if "resultados_pesquisa" not in st.session_state:
    st.session_state["resultados_pesquisa"] = []
if "pesquisa_realizada" not in st.session_state:
    st.session_state["pesquisa_realizada"] = False
if "cidade_pesquisa" not in st.session_state:
    st.session_state["cidade_pesquisa"] = "Todas"

_col_input, _col_btn = st.columns([4, 1])
with _col_input:
    termo_digitado = st.text_input(
        "Digite o número do medidor ou da unidade consumidora",
        key="termo_pesquisa_input",
        label_visibility="collapsed",
        placeholder="UC ou número do medidor",
    )
with _col_btn:
    pesquisar = st.button(
        "🔎",
        use_container_width=True,
        help="Pesquisar",
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
opcoes_status = ["Todos", "Com localização", "Sem dados"]
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


def tem_link_maps(r):
    try:
        return bool(str(r.get("link_maps") or "").strip())
    except Exception:
        return False

if status_sel == "Com localização":
    resultado = [r for r in resultado if tem_coord(r) or tem_link_maps(r)]
elif status_sel == "Sem dados":
    resultado = [r for r in resultado if not tem_coord(r) and not tem_link_maps(r)]

if resultado:
    for idx, row in enumerate(resultado):
        st.html("<hr style='margin:6px 0;border-color:#444'>")

        lat = row.get("latitude")
        lon = row.get("longitude")
        link_maps = str(row.get("link_maps") or "").strip()
        has_coord = lat is not None and lon is not None and str(lat).strip() != "" and str(lon).strip() != ""
        has_link = bool(link_maps)
        has_location = has_coord or has_link

        status_pill = "✅ Com localização" if has_location else "⬜ Sem dados"
        coord_info = f"<br><small>🌍 {lat}, {lon}</small>" if has_coord else ""
        st.html(f"""<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:10px 14px;margin-bottom:4px">
  <b>👤 {row.get('cliente','')}</b><br>
  <small>📟 {row.get('medidor','')} &nbsp;|&nbsp; UC: {row.get('uc','')}</small><br>
  <small>📍 {row.get('endereco','')} — {row.get('cidade','')}</small><br>
  <small>{status_pill}</small>{coord_info}
</div>""")

        if has_location:
            url_maps = montar_url_maps(lat, lon, link_maps)
            if url_maps:
                st.link_button("🗺️ Abrir no Google Maps", url_maps, type="primary", use_container_width=True)

        expander_label = "✏️ Atualizar localização" if has_location else "➕ Inserir localização"
        with st.expander(expander_label, expanded=not has_location):
            opcao_localizacao = st.radio(
                "Escolha o método:",
                [
                    "Capturar GPS do dispositivo",
                    "Inserir coordenadas manualmente",
                    "Colar link do Google Maps",
                ],
                key=f"opcao_localizacao_{idx}",
            )

            if opcao_localizacao == "Capturar GPS do dispositivo":
                loc = get_geolocation()
                if loc:
                    lat_gps, lon_gps = loc["coords"]["latitude"], loc["coords"]["longitude"]
                    st.success(f"Coordenada detectada: ({lat_gps}, {lon_gps})")
                    if st.button("Salvar localização", key=f"salvar_gps_{idx}"):
                        if atualizar_localizacao(row["id"], float(lat_gps), float(lon_gps), None):
                            atualizar_resultado_em_sessao(row["id"], float(lat_gps), float(lon_gps), None)
                            st.success("Localização salva com sucesso!")
                            st.rerun()

            elif opcao_localizacao == "Inserir coordenadas manualmente":
                coord_input = st.text_input(
                    "Informe latitude e longitude:",
                    key=f"manual_localizacao_{idx}",
                )
                if st.button("Salvar localização", key=f"salvar_manual_{idx}"):
                    localizacao_manual = resolver_localizacao_manual(coord_input)
                    lat_manual = localizacao_manual["latitude"]
                    lon_manual = localizacao_manual["longitude"]

                    if localizacao_manual["erro"] or lat_manual is None or lon_manual is None:
                        st.error(
                            localizacao_manual["erro"]
                            or "Não foi possível interpretar a localização. Informe coordenadas válidas ou cole um link do Google Maps."
                        )
                    else:
                        if atualizar_localizacao(row["id"], float(lat_manual), float(lon_manual), None):
                            atualizar_resultado_em_sessao(row["id"], float(lat_manual), float(lon_manual), None)
                            st.success("Localização salva com sucesso!")
                            st.rerun()

            elif opcao_localizacao == "Colar link do Google Maps":
                link_input = st.text_input(
                    "Cole o link do Google Maps:",
                    key=f"link_localizacao_{idx}",
                )
                if st.button("Salvar localização", key=f"salvar_link_{idx}"):
                    if not eh_url_maps(link_input):
                        st.error("Cole um link válido do Google Maps.")
                    else:
                        localizacao_link = resolver_localizacao_manual(link_input)
                        if atualizar_localizacao(
                            row["id"],
                            localizacao_link["latitude"],
                            localizacao_link["longitude"],
                            localizacao_link["link_maps"],
                        ):
                            atualizar_resultado_em_sessao(
                                row["id"],
                                localizacao_link["latitude"],
                                localizacao_link["longitude"],
                                localizacao_link["link_maps"],
                            )
                            st.success("Localização salva com sucesso!")
                            st.rerun()
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

    # Cidade
    if cidade == "Todas":
        cidades_disponiveis = listar_cidades()
        if cidades_disponiveis:
            cidade_novo = st.selectbox("Cidade do cliente", cidades_disponiveis)
        else:
            cidade_novo = st.text_input("Cidade do cliente")
    else:
        cidade_novo = cidade

    st.markdown("#### 📍 Localização da unidade")
    metodo_localizacao_novo = st.radio(
        "Como deseja informar a localização?",
        [
            "Capturar GPS do dispositivo",
            "Inserir coordenadas manualmente",
            "Colar link do Google Maps",
        ],
        key="metodo_localizacao_novo",
    )

    lat_final = None
    lon_final = None
    link_maps_final = None
    erro_localizacao_novo = None

    if metodo_localizacao_novo == "Capturar GPS do dispositivo":
        loc_novo = get_geolocation()
        if loc_novo:
            lat_final = float(loc_novo["coords"]["latitude"])
            lon_final = float(loc_novo["coords"]["longitude"])
            st.success(f"Coordenada detectada: ({lat_final}, {lon_final})")
        else:
            st.info("Permita o acesso à localização para capturar o GPS do dispositivo.")

    elif metodo_localizacao_novo == "Inserir coordenadas manualmente":
        localizacao_manual_novo = st.text_input(
            "Informe latitude e longitude:",
            key="localizacao_manual_novo",
        )
        if localizacao_manual_novo.strip():
            resolucao_manual_novo = resolver_localizacao_manual(localizacao_manual_novo)
            erro_localizacao_novo = resolucao_manual_novo["erro"]
            lat_final = resolucao_manual_novo["latitude"]
            lon_final = resolucao_manual_novo["longitude"]

    elif metodo_localizacao_novo == "Colar link do Google Maps":
        link_maps_novo = st.text_input(
            "Cole o link do Google Maps:",
            key="link_maps_novo",
        )
        if link_maps_novo.strip():
            if not eh_url_maps(link_maps_novo):
                erro_localizacao_novo = "Cole um link válido do Google Maps."
            else:
                resolucao_link_novo = resolver_localizacao_manual(link_maps_novo)
                erro_localizacao_novo = resolucao_link_novo["erro"]
                lat_final = resolucao_link_novo["latitude"]
                lon_final = resolucao_link_novo["longitude"]
                link_maps_final = resolucao_link_novo["link_maps"]

    if st.button("Salvar novo cliente"):
        if metodo_localizacao_novo == "Capturar GPS do dispositivo":
            localizacao_valida = lat_final is not None and lon_final is not None
        elif metodo_localizacao_novo == "Inserir coordenadas manualmente":
            localizacao_valida = erro_localizacao_novo is None and lat_final is not None and lon_final is not None
        else:
            localizacao_valida = erro_localizacao_novo is None and bool(str(link_maps_final or "").strip())

        if not localizacao_valida:
            if erro_localizacao_novo:
                st.error(erro_localizacao_novo)
            else:
                st.error("Informe a localização da unidade por GPS, coordenadas manuais ou link do Google Maps.")
        else:
            ok = cadastrar_unidade({
                "cidade": cidade_novo,
                "uc": nova_uc,
                "medidor": novo_medidor,
                "cliente": novo_nome,
                "endereco": novo_endereco,
                "latitude": lat_final,
                "longitude": lon_final,
                "link_maps": link_maps_final,
            })
            if ok:
                st.success("Cliente cadastrado com sucesso!")
                del st.session_state["novo_cliente"]
                st.rerun()
