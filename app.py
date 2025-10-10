
import streamlit as st
import pandas as pd
import re
import unidecode
from urllib.parse import unquote

# ========================
# CONFIGURAÇÃO INICIAL
# ========================
st.set_page_config(page_title="Localizador de Unidades Consumidoras", layout="centered")
st.title("📍 Localizador de Unidades Consumidoras")

# ========================
# LEITURA E NORMALIZAÇÃO
# ========================
try:
    df = pd.read_excel("dados_araras_filtrado.xlsx")

    # Normaliza os nomes das colunas
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .map(unidecode.unidecode)
    )

    # Renomeia colunas conhecidas
    df.rename(columns={
        "uc/numero": "UC/número",
        "cidade": "Cidade",
        "nome do cliente": "Nome do cliente",
        "endereco": "Endereço",
        "equipamento": "Equipamento",
        "valor latitude": "valor latitude",
        "valor longitude": "valor longitude"
    }, inplace=True)

except Exception as e:
    st.error(f"Erro ao carregar planilha: {e}")
    st.stop()

# ========================
# INTERFACE PRINCIPAL
# ========================
st.subheader("🔎 Buscar cliente")

opcao_busca = st.radio("Buscar por:", ["Número do medidor", "UC/número"])
valor_busca = st.text_input("Digite o número para localizar")

if st.button("Buscar"):
    coluna_busca = "UC/número" if opcao_busca == "UC/número" else "Equipamento"
    try:
        resultado = df[df[coluna_busca].astype(str).str.contains(valor_busca.strip(), case=False, na=False)]
    except KeyError:
        st.error("Erro: a coluna de busca não foi encontrada no arquivo Excel.")
        st.stop()

    if not resultado.empty:
        st.success(f"{len(resultado)} resultado(s) encontrado(s).")
        for _, row in resultado.iterrows():
            st.markdown(f"**Cliente:** {row.get('Nome do cliente', '')}")
            st.write(f"**UC:** {row.get('UC/número', '')}")
            st.write(f"**Cidade:** {row.get('Cidade', '')}")
            st.write(f"**Endereço:** {row.get('Endereço', '')}")
            st.write(f"**Equipamento:** {row.get('Equipamento', '')}")
            
            lat, lon = row.get("valor latitude"), row.get("valor longitude")
            if pd.notna(lat) and pd.notna(lon):
                st.markdown(f"[📍 Abrir no Google Maps](https://www.google.com/maps?q={lat},{lon})")
            else:
                st.warning("Sem coordenadas registradas.")
            st.divider()
    else:
        st.warning("Nenhum cliente encontrado.")

# ========================
# ATUALIZAÇÃO DE COORDENADAS
# ========================
st.subheader("📌 Completar/Atualizar coordenadas")
aba = st.tabs(["📍 Capturar GPS", "✏️ Inserir manualmente"])[1]

with aba:
    coord_input = st.text_input("Cole aqui a coordenada (ex.: -22.3577,-47.3627 ou link do Google Maps)")
    salvar = st.button("Salvar coordenada (manual)")

    if salvar:
        try:
            # Extrai coordenadas numéricas do texto
            texto = unquote(coord_input)
            match = re.findall(r"-?\d+\.\d+", texto)
            if len(match) >= 2:
                lat, lon = match[0], match[1]
                st.success(f"Cliente atualizado com sucesso! Nova coordenada: ({lat}, {lon})")
            else:
                st.error("Não consegui interpretar a coordenada. Verifique o formato e tente novamente.")
        except Exception as e:
            st.error(f"Erro ao processar coordenada: {e}")
