import sys
import re
import requests
import time
import os
import json
import base64
import math
from datetime import datetime
import streamlit as st
import pandas as pd
from PIL import Image
import pytesseract
import pydeck as pdk
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Tenta importar o leitor de PDF de forma segura
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Configuração da Página
st.set_page_config(page_title="LoGuii - Rotas", layout="wide", page_icon="logo.png")

# Ajuste do Tesseract para Windows/Nuvem
if sys.platform.startswith('win'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Diretórios e Arquivos Locais
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_caricatura = os.path.join(diretorio_atual, "caricatura.png")
caminho_logo = os.path.join(diretorio_atual, "logo.png")
arquivo_historico = os.path.join(diretorio_atual, "historico_rotas.json")
arquivo_pendentes = os.path.join(diretorio_atual, "pendentes.json")

# --- LEITURA DO ARQUIVO DE ESTOQUE ---
@st.cache_data
def carregar_estoque():
    itens = []
    caminho_pdf_min = os.path.join(diretorio_atual, "estoque.pdf")
    caminho_pdf_mai = os.path.join(diretorio_atual, "estoque.PDF")
    
    caminho_correto = None
    if os.path.exists(caminho_pdf_min):
        caminho_correto = caminho_pdf_min
    elif os.path.exists(caminho_pdf_mai):
        caminho_correto = caminho_pdf_mai
    
    if caminho_correto and PyPDF2 is not None:
        try:
            with open(caminho_correto, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            line = line.strip()
                            match = re.search(r'^(\d{3,6})\s+(.+?)(?=\s+MARCA PADRAO|\s+MARCA\b|\s{2,})', line, re.IGNORECASE)
                            if match:
                                codigo = match.group(1).strip()
                                descricao = match.group(2).strip()
                                itens.append(f"{codigo} - {descricao}")
            if itens:
                return sorted(list(set(itens)))
        except Exception as e:
            st.sidebar.error(f"Erro ao ler arquivo de estoque: {e}")
            
    return ["Exemplo: Fita Adesiva - Cód 101", "Exemplo: Caixa Parda - Cód 102"]

lista_estoque = carregar_estoque()

# --- BANCO DE DADOS DE USUÁRIOS BLINDADO ---
USUARIOS_CADASTRADOS = {
    "admin": "123456",
    "expedicao": "loguii2026",
    "motorista": "uniaologuii"
}

# --- SISTEMA DE PERSISTÊNCIA DE LOGIN (SOBREVIVE AO F5) ---
if "autenticado" not in st.session_state: 
    if hasattr(st, "query_params") and st.query_params.get("auth") == "loguii_ok":
        st.session_state.autenticado = True
    else:
        st.session_state.autenticado = False

# --- TELA DE LOGIN ---
if not st.session_state.autenticado:
    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=250)
        
        st.title("🔒 Acesso Restrito - LoGuii")
        st.markdown("Faça o login para acessar o sistema logístico.")
        
        user_login = st.text_input("Usuário")
        pass_login = st.text_input("Senha", type="password")
        
        if st.button("Entrar no Sistema", type="primary", use_container_width=True):
            usuario_limpo = user_login.strip().lower()
            
            if usuario_limpo in USUARIOS_CADASTRADOS and USUARIOS_CADASTRADOS[usuario_limpo] == pass_login:
                st.session_state.autenticado = True
                if hasattr(st, "query_params"):
                    st.query_params["auth"] = "loguii_ok"
                st.rerun() 
            else: 
                st.error("❌ Usuário ou senha incorretos. Verifique e tente novamente.")
    st.stop() 

# --- FUNÇÕES DE SALVAMENTO DOS PENDENTES ---
def salvar_pendentes(lista):
    with open(arquivo_pendentes, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=4)

def carregar_pendentes():
    if os.path.exists(arquivo_pendentes):
        try:
            with open(arquivo_pendentes, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

# --- FUNÇÃO DA MARCA D'ÁGUA ---
def aplicar_marca_dagua(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        css = f"""
        <style>
        [data-testid="stAppViewContainer"] > .main::before {{
            content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background-image: url("data:image/png;base64,{encoded_string}");
            background-size: 45%; background-position: center; background-repeat: no-repeat;
            background-attachment: fixed; opacity: 0.10; z-index: -1;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)

aplicar_marca_dagua(caminho_caricatura)

# --- CABEÇALHO DA PÁGINA PRINCIPAL ---
col_texto, col_imagem = st.columns([5, 1])
with col_texto:
    st.title("🚚 LoGuii Solução Logística")
    st.markdown("Gerencie pedidos pendentes, agrupe por raio de 7km e gere rotas otimizadas.")
with col_imagem:
    if os.path.exists(caminho_caricatura):
        st.image(caminho_caricatura, width=130)

if "pendentes" not in st.session_state:
    st.session_state.pendentes = carregar_pendentes()

# --- INTELIGÊNCIA GEOGRÁFICA COM CACHE DE PERFORMANCE ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

@st.cache_data(show_spinner=False, ttl=86400)
def geocodificar(endereco):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'LoGuiiApp/1.0'}
    query = endereco if "Franca" in endereco else f"{endereco}, Franca, SP, Brasil"
    params = {'q': query, 'format': 'json', 'limit': 1}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=4)
        dados = res.json()
        if dados:
            return float(dados[0]['lat']), float(dados[0]['lon'])
    except: 
        pass
    
    if "," in endereco:
        rua = endereco.split(",")[0].strip()
        try:
            res = requests.get(url, headers=headers, params={'q': f"{rua}, Franca, SP, Brasil", 'format': 'json', 'limit': 1}, timeout=4)
            dados = res.json()
            if dados:
                return float(dados[0]['lat']), float(dados[0]['lon'])
        except: 
            pass
            
    return None, None

def atualizar_agrupamentos(pendentes):
    n = len(pendentes)
    if n == 0: return

    for p in pendentes:
        if not p.get('lat') or not p.get('lon'):
            lat, lon = geocodificar(p['endereco'])
            if lat and lon:
                p['lat'], p['lon'] = float(lat), float(lon)

    adj = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i+1, n):
            if pendentes[i].get('lat') and pendentes[j].get('lat'):
                d = haversine(float(pendentes[i]['lat']), float(pendentes[i]['lon']), float(pendentes[j]['lat']), float(pendentes[j]['lon']))
                if d <= 7.0:
                    adj[i].append(j)
                    adj[j].append(i)
    
    visited = set()
    grupo_id = 1
    for i in range(n):
        if i not in visited:
            queue = [i]
            visited.add(i)
            componente = [i]
            
            while queue:
                curr = queue.pop(0)
                for viz in adj[curr]:
                    if viz not in visited:
                        visited.add(viz)
                        queue.append(viz)
                        componente.append(viz)
            
            nome_grupo = None
            for c in componente:
                if pendentes[c].get('fixo') and pendentes[c].get('grupo'):
                    nome_grupo = pendentes[c]['grupo']
                    break
            
            if not nome_grupo:
                nome_grupo = f"Rota {grupo_id}"
                grupo_id += 1
                
            for c in componente:
                if not pendentes[c].get('fixo'):
                    pendentes[c]['grupo'] = nome_grupo

# --- PLANILHA DE CLIENTES ---
@st.cache_data
def carregar_clientes():
    arquivos = [
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xlsx"),
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xls"),
        os.path.join(diretorio_atual, "clientes.xlsx"),
        "Listagem_Clientes_de_Franca.xlsx"
    ]
    for arquivo in arquivos:
        if os.path.exists(arquivo):
            try:
                df = pd.read_excel(arquivo)
                df.columns = df.columns.str.strip()
                if 'Código' in df.columns:
                    df['Código'] = df['Código'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                if 'Numero' in df.columns:
                    df['Numero'] = df['Numero'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                return df, True, arquivo
            except Exception as e:
                return pd.DataFrame(), False, f"Erro: {str(e)}"
    return pd.DataFrame(), False, "Planilha não encontrada."

df_clientes, status_ok, msg_erro = carregar_clientes()

# --- MENU LATERAL (SIDEBAR) ---
if os.path.exists(caminho_logo):
    st.sidebar.image(caminho_logo, use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 

st.sidebar.header("🔍 1. Adicionar à Fila")
if status_ok and not df_clientes.empty:
    colunas_necessarias = ['Código', 'Cliente', 'Endereco', 'Numero']
    if all(col in df_clientes.columns for col in colunas_necessarias):
        opcoes = df_clientes['Código'] + " - " + df_clientes['Cliente']
        cliente_selecionado = st.sidebar.selectbox("Digite o Código ou Nome do Cliente:", options=["Selecione..."] + opcoes.tolist())
        if st.sidebar.button("➕ Enviar para Pendentes", type="primary"):
            if cliente_selecionado != "Selecione...":
                with st.spinner("Adicionando e mapeando endereço..."):
                    codigo_busca = cliente_selecionado.split(" - ")[0]
                    dados_cli = df_clientes[df_clientes['Código'] == codigo_busca].iloc[0]
                    rua = str(dados_cli['Endereco']).strip().split('-')[0].strip()
                    num = str(dados_cli['Numero']).strip()
                    endereco_completo = f"{rua}, {num}" if num.lower() != 'nan' and num else rua
                    
                    lat, lon = geocodificar(endereco_completo)
                    
                    st.session_state.pendentes.append({
                        "uid": f"bd_{codigo_busca}_{time.time()}",
                        "cliente": str(dados_cli['Cliente']),
                        "endereco": endereco_completo,
                        "pedido_num": "", "urgente": False, "horario": "",
                        "selecionado": True, "itens": [], "grupo": "Calculando...", "fixo": False,
                        "lat": float(lat) if lat else None, 
                        "lon": float(lon) if lon else None
                    })
                    atualizar_agrupamentos(st.session_state.pendentes)
                    salvar_pendentes(st.session_state.pendentes)
                    st.sidebar.success(f"{dados_cli['Cliente']} adicionado!")
                    st.rerun()
            else:
                st.sidebar.warning("Selecione um cliente primeiro.")
else:
    st.sidebar.error("Planilha de clientes não encontrada!")

st.sidebar.divider()

st.sidebar.header("📁 2. Adicionar por Imagem")
modo_imagem = st.sidebar.radio("Como deseja enviar a imagem?", ["Fazer Upload", "Tirar Foto"])
imagens_para_processar = []
if modo_imagem == "Fazer Upload":
    uploaded_files = st.sidebar.file_uploader("Envie a imagem", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploaded_files:
        imagens_para_processar.extend(uploaded_files)
else:
    foto_camera = st.sidebar.camera_input("📸 Tire a foto")
    if foto_camera:
        imagens_para_processar.append(foto_camera)

def extrair_dados_imagem(imagem):
    texto = pytesseract.image_to_string(imagem, lang="por")
    texto_cliente = texto[texto.find("Cliente:"):] if "Cliente:" in texto else texto[texto.find("CNPJ/CPF:"):] if "CNPJ/CPF:" in texto else texto
    cliente_match = re.search(r"Cliente:\s*\d+\s*-\s*(.*?)(?:-|\n)", texto, re.IGNORECASE) or re.search(r"Cliente:\s*(.*)", texto, re.IGNORECASE)
    cliente = cliente_match.group(1).strip() if cliente_match else "Não identificado"
    linha_endereco_match = re.search(r"Endereço:\s*([^\n]*)", texto_cliente, re.IGNORECASE)
    rua, numero = "", ""
    if linha_endereco_match:
        linha = linha_endereco_match.group(1)
        rua = re.split(r'\s*-\s*NULL|\s*N[°ºoOwW]|\s*w[°º]|\s*CEP', linha, flags=re.IGNORECASE)[0].strip().split('-')[0].strip()
        rua = re.sub(r'[\-,\.\s]+$', '', rua)
        numero_match = re.search(r"(?:N[°ºoOwW\.\*]|\bw[°º]|N\b|- w[°º])\s*(\d+)", linha, re.IGNORECASE) or re.search(r"(\d+)\s*CEP", linha, re.IGNORECASE)
        numero = numero_match.group(1).strip() if numero_match else ""
    
    end_completo = f"{rua}, {numero}" if (rua and numero) else rua if rua else "Endereço não identificado"
    lat, lon = geocodificar(end_completo) if end_completo != "Endereço não identificado" else (None, None)
    
    return {
        "cliente": cliente, "endereco": end_completo, 
        "pedido_num": "", "urgente": False, "horario": "", 
        "selecionado": True, "itens": [], "grupo": "Calculando...", "fixo": False, 
        "lat": float(lat) if lat else None, "lon": float(lon) if lon else None
    }

if imagens_para_processar:
    with st.spinner("Lendo imagens e mapeando..."):
        for arq_imagem in imagens_para_processar:
            image = Image.open(arq_imagem)
            file_id = getattr(arq_imagem, "name", f"camera_{time.time()}")
            if not any(p.get("uid") == file_id for p in st.session_state.pendentes):
                dados = extrair_dados_imagem(image)
                dados["uid"] = file_id
                st.session_state.pendentes.append(dados)
        atualizar_agrupamentos(st.session_state.pendentes)
        salvar_pendentes(st.session_state.pendentes)
        st.rerun()

st.sidebar.divider()
if st.sidebar.button("🚪 Sair do Sistema (Logout)"):
    st.session_state.autenticado = False
    if hasattr(st, "query_params") and "auth" in st.query_params:
        del st.query_params["auth"]
    st.rerun()

# --- LISTAGEM DE PENDENTES E MAPA PYDECK OTIMIZADO COM TEMA NATIVO ---
st.subheader("📋 Fila de Pedidos Pendentes")
st.markdown("Pedidos distantes até 7km são agrupados automaticamente. O mapa interativo exibe todos os pontos localizados.")

st.session_state.pendentes.sort(key=lambda x: (x.get('grupo', ''), not x.get('urgente', False)))

if st.session_state.pendentes:
    dados_mapa = []
    for p in st.session_state.pendentes:
        if p.get('lat') and p.get('lon'):
            dados_mapa.append({
                "lat": float(p['lat']), 
                "lon": float(p['lon']),
                "Cliente": p.get("cliente", "Desconhecido"),
                "Endereco": p.get("endereco", "Não informado"),
                "Grupo": p.get("grupo", "Sem Grupo")
            })
            
    if dados_mapa:
        df_mapa = pd.DataFrame(dados_mapa)
        with st.expander("📍 Visualizar Mapa Interativo de Entregas", expanded=True):
            layer = pdk.Layer(
