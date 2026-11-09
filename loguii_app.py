import sys
import re
import requests
import time
import os
import json
import base64
import math
import unicodedata
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
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
st.set_page_config(page_title="Painel União Embalagens", layout="wide", page_icon="logo.png")

# Ajuste do Tesseract para Windows/Nuvem
if sys.platform.startswith('win'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Diretórios e Arquivos Locais
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_caricatura = os.path.join(diretorio_atual, "caricatura.png")
caminho_logo = os.path.join(diretorio_atual, "logo.png")
arquivo_historico = os.path.join(diretorio_atual, "historico_rotas.json")
arquivo_pendentes = os.path.join(diretorio_atual, "pendentes.json")

# ==========================================================
# ☁️ INTEGRAÇÃO COM FIREBASE (BANCO DE DADOS EM NUVEM)
# ==========================================================
FIREBASE_URL = "https://loguii-default-rtdb.firebaseio.com"

def salvar_pendentes(lista):
    try:
        requests.put(f"{FIREBASE_URL}/pendentes.json", json=lista)
    except: 
        with open(arquivo_pendentes, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=4)

def carregar_pendentes():
    lista = []
    try:
        res = requests.get(f"{FIREBASE_URL}/pendentes.json")
        if res.status_code == 200 and res.json() is not None:
            lista = res.json()
    except:
        if os.path.exists(arquivo_pendentes):
            try:
                with open(arquivo_pendentes, "r", encoding="utf-8") as f:
                    lista = json.load(f)
            except: pass
            
    for item in lista:
        if 'status' not in item:
            item['status'] = 'espera'
    return lista

def salvar_historico(lista):
    try:
        requests.put(f"{FIREBASE_URL}/historico.json", json=lista)
    except:
        with open(arquivo_historico, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=4)

def carregar_historico():
    try:
        res = requests.get(f"{FIREBASE_URL}/historico.json")
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except:
        if os.path.exists(arquivo_historico):
            try:
                with open(arquivo_historico, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
    return []

# --- FROTA OFICIAL CADASTRADA ---
FROTA_UNIAO = [
    "Moto 1", 
    "Moto 2", 
    "Fiorino 1", 
    "Fiorino 2", 
    "Caminhão HR", 
    "Caminhão Bongo", 
    "Caminhão Mercedes"
]

# --- FUNÇÃO AUXILIAR PARA MAPAS (REMOVER ACENTOS) ---
def remover_acentos(txt):
    if not txt: return ""
    txt = str(txt)
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

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

# --- BANCO DE DADOS DE USUÁRIOS ATUALIZADO ---
USUARIOS_CADASTRADOS = {
    "admin": "123456",
    "estoque": "alex123",
    "escritorio": "041020"
}

# --- SISTEMA DE NAVEGAÇÃO E PERSISTÊNCIA NA URL (F5 SAFE) ---
if "autenticado" not in st.session_state: 
    if hasattr(st, "query_params") and st.query_params.get("auth") == "loguii_ok":
        st.session_state.autenticado = True
    else:
        st.session_state.autenticado = False

if "pagina_atual" not in st.session_state:
    if hasattr(st, "query_params") and "pagina" in st.query_params:
        st.session_state.pagina_atual = st.query_params["pagina"]
    else:
        st.session_state.pagina_atual = "menu"

def mudar_pagina(nova_pagina):
    st.session_state.pagina_atual = nova_pagina
    if hasattr(st, "query_params"):
        st.query_params["pagina"] = nova_pagina
    st.rerun()

def voltar_menu():
    st.session_state.pagina_atual = "menu"
    if hasattr(st, "query_params") and "pagina" in st.query_params:
        del st.query_params["pagina"]
    st.rerun()

# --- TELA DE LOGIN ---
if not st.session_state.autenticado:
    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=250)
        
        st.title("🔒 Acesso Restrito Corporativo")
        st.markdown("Faça o login para acessar os sistemas da União Embalagens.")
        
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


# ==========================================================
# 🏢 TELA 0: MENU HUB (ESCOLHA DO SISTEMA)
# ==========================================================
if st.session_state.autenticado and st.session_state.pagina_atual == "menu":
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    col_logo, col_vazia = st.columns([1, 4])
    with col_logo:
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=180)
            
    st.title("🏢 Painel Corporativo")
    st.markdown("Selecione qual sistema você deseja acessar:")
    st.divider()
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        st.markdown("### 🚚 LoGuii Solução Logística")
        st.markdown("Sistema completo com Dashboard, roteirização inteligente, gestão de frotas e checklists.")
        if st.button("Acessar LoGuii", use_container_width=True, type="primary"):
            mudar_pagina("loguii")
            
    with col2:
        st.markdown("### 🔗 Links Úteis da Empresa")
        st.markdown("Acesso rápido e cópia instantânea de CNPJs, endereços de estoques, PIX e contatos departamentais.")
        if st.button("Acessar Links Úteis", use_container_width=True):
            mudar_pagina("links")
            
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sair do Sistema (Logout)", use_container_width=True):
        st.session_state.autenticado = False
        if hasattr(st, "query_params"):
            st.query_params.clear()
        st.rerun()
        
    st.stop()


# ==========================================================
# 🔗 TELA 1: LINKS ÚTEIS (HTML INJETADO)
# ==========================================================
if st.session_state.autenticado and st.session_state.pagina_atual == "links":
    
    if st.sidebar.button("⬅️ Voltar ao Menu Principal", type="primary", use_container_width=True):
        voltar_menu()
    st.sidebar.divider()

    st.title("🔗 Links Úteis e Cadastros - União Embalagens")
    
    base64_logo = ""
    if os.path.exists(caminho_logo):
        with open(caminho_logo, "rb") as image_file:
            base64_logo = f"data:image/png;base64,{base64.b64encode(image_file.read()).decode()}"

    html_code = f"""
    <!DOCTYPE html>
    <html lang="pt-BR" class="light">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{ darkMode: 'class', }}
        </script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        <style>
            .copy-card {{ perspective: 1000px; }}
            .title-container {{ transition: opacity 0.3s ease-in-out; opacity: 1; }}
            .info-container {{ transition: opacity 0.3s ease-in-out; opacity: 0; pointer-events: none; }}
            .copy-card:hover .title-container {{ opacity: 0; }}
            .copy-card:hover .info-container {{ opacity: 1; }}
            @keyframes toast-enter {{ from {{ opacity: 0; transform: translateY(100%) translateX(-50%); }} to {{ opacity: 1; transform: translateY(0) translateX(-50%); }} }}
            @keyframes toast-leave {{ from {{ opacity: 1; transform: translateY(0) translateX(-50%); }} to {{ opacity: 0; transform: translateY(100%) translateX(-50%); }} }}
            .toast-notification {{ animation: toast-enter 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; left: 50%; }}
            .toast-notification.leaving {{ animation: toast-leave 0.3s ease-in forwards; }}
        </style>
    </head>
    <body class="bg-gray-50 dark:bg-gray-900 transition-colors duration-300 min-h-screen flex flex-col items-center py-12 px-4 font-sans relative">
        <button id="theme-toggle" class="absolute top-6 right-6 p-3 rounded-full bg-gray-200 dark:bg-gray-800 text-gray-800 dark:text-yellow-400 hover:bg-gray-300 dark:hover:bg-gray-700 transition-all shadow-md focus:outline-none">
            <i id="theme-icon" class="fa-solid fa-moon text-xl"></i>
        </button>
        <div class="mb-12 flex flex-col items-center justify-center dark:bg-white dark:p-4 dark:rounded-2xl dark:shadow-lg transition-all duration-300">
            <img src="{base64_logo}" alt="União Embalagens Logo" class="h-24 md:h-32 object-contain" onerror="this.style.display='none';">
        </div>
        <div class="w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-4" id="buttons-container"></div>
        <div id="toast-container" class="fixed bottom-8 z-50 pointer-events-none flex flex-col gap-3"></div>

        <script>
            const themeToggleBtn = document.getElementById('theme-toggle');
            const themeIcon = document.getElementById('theme-icon');
            const htmlElement = document.documentElement;

            if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
                htmlElement.classList.add('dark');
                themeIcon.classList.replace('fa-moon', 'fa-sun');
            }}

            themeToggleBtn.addEventListener('click', () => {{
                htmlElement.classList.toggle('dark');
                if (htmlElement.classList.contains('dark')) {{
                    localStorage.theme = 'dark';
                    themeIcon.classList.replace('fa-moon', 'fa-sun');
                }} else {{
                    localStorage.theme = 'light';
                    themeIcon.classList.replace('fa-sun', 'fa-moon');
                }}
            }});

            const data = [
                {{ title: "Whatsapp Vendas", info: "16 99969-4903", icon: "fa-brands fa-whatsapp" }},
                {{ title: "Whatsapp Compras", info: "16 99232-2820", icon: "fa-solid fa-cart-shopping" }},
                {{ title: "Whatsapp Financeiro", info: "16 99405-0191", icon: "fa-solid fa-money-bill-wave" }},
                {{ title: "Endereço Loja", info: "Avenida Nazira Aidar, 5061 - Jd Moema", icon: "fa-solid fa-store" }},
                {{ title: "Endereço Estoque", info: "Rua Doutor Ivom Rodrigues Pereira, 5078 - Jd Moema", icon: "fa-solid fa-box-open" }},
                {{ title: "Endereço CD", info: "Rua José Luiz Garcia, 3681, Jd Guanabara", icon: "fa-solid fa-warehouse" }},
                {{ title: "CNPJ Unigens", info: "51.662.217/0001-06", icon: "fa-solid fa-id-card" }},
                {{ title: "CNPJ E.L De Carvalho", info: "08.920.840/0001-84", icon: "fa-solid fa-id-card" }},
                {{ title: "Observação NF SJB", info: "RRF 1,2% - R$: -- CONFORME INSTRUÇÃO NORMATIVA 1234 DE 2012 ARTIGO II PARAGRAFO 6", icon: "fa-solid fa-file-invoice" }},
                {{ title: "Chave PIX", info: "(16) 99969-4903 - Sicoob - EL De Carvalho", icon: "fa-brands fa-pix" }},
                {{ title: "Email Licitações", info: "unigenslicitacoes@gmail.com", icon: "fa-solid fa-envelope" }}
            ];

            const container = document.getElementById('buttons-container');

            data.forEach((item) => {{
                const buttonHtml = `
                    <button 
                        onclick="copyToClipboard('${{item.info.replace(/'/g, "\\'")}}')"
                        class="copy-card relative w-full h-24 bg-red-600 rounded-xl shadow-md hover:shadow-lg hover:-translate-y-1 transform transition-all duration-300 overflow-hidden group cursor-pointer focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                    >
                        <div class="absolute inset-0 flex flex-col items-center justify-center p-4">
                            <div class="title-container absolute inset-0 flex flex-col items-center justify-center text-white w-full px-2">
                                <i class="${{item.icon}} text-3xl mb-2"></i>
                                <h2 class="text-lg font-bold text-center leading-tight truncate w-full">${{item.title}}</h2>
                            </div>
                            <div class="info-container absolute inset-0 flex items-center justify-center text-white w-full px-4">
                                <p class="info-text text-sm md:text-base font-medium text-center break-words w-full">${{item.info}}</p>
                            </div>
                        </div>
                    </button>
                `;
                container.innerHTML += buttonHtml;
            }});

            function showToast(message) {{
                const toastContainer = document.getElementById('toast-container');
                const toast = document.createElement('div');
                toast.className = 'toast-notification absolute bottom-0 bg-green-500 text-white px-6 py-3 rounded-full shadow-2xl font-bold flex items-center gap-2 border-2 border-green-400 whitespace-nowrap';
                toast.innerHTML = `<i class="fa-solid fa-circle-check text-xl"></i> ${{message}}`;
                toastContainer.innerHTML = '';
                toastContainer.appendChild(toast);
                setTimeout(() => {{
                    toast.classList.add('leaving');
                    toast.addEventListener('animationend', () => {{ toast.remove(); }});
                }}, 2500);
            }}

            function copyToClipboard(textToCopy) {{
                const textArea = document.createElement("textarea");
                textArea.value = textToCopy;
                textArea.style.position = "absolute";
                textArea.style.left = "-999999px";
                document.body.prepend(textArea);
                textArea.select();
                try {{
                    document.execCommand('copy');
                    showToast("Copiado com sucesso!");
                }} catch (err) {{
                    alert("Não foi possível copiar automaticamente.");
                }} finally {{
                    textArea.remove();
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    components.html(html_code, height=900, scrolling=True)


# ==========================================================
# 🚚 TELA 2: LOGUII (SISTEMA DE ROTAS & DASHBOARD)
# ==========================================================
if st.session_state.autenticado and st.session_state.pagina_atual == "loguii":
    
    if st.sidebar.button("⬅️ Voltar ao Menu Principal", type="primary", use_container_width=True):
        voltar_menu()
    st.sidebar.divider()

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
        st.markdown("Painel Operacional, Gestão de Frota e Roteirização Inteligente.")
    with col_imagem:
        if os.path.exists(caminho_caricatura):
            st.image(caminho_caricatura, width=130)

    if "pendentes" not in st.session_state:
        st.session_state.pendentes = carregar_pendentes()

    # ==========================================================
    # 📊 1. DASHBOARD LOGÍSTICO (NOVO)
    # ==========================================================
    st.markdown("### 📊 Dashboard Operacional")
    
    historico_geral = carregar_historico()
    total_pedidos_galpao = len([p for p in st.session_state.pendentes if p.get('status', 'espera') == 'espera'])
    total_pedidos_caminhao = len([p for p in st.session_state.pendentes if p.get('status', 'espera') == 'rota'])
    total_rotas_realizadas = len(historico_geral)
    
    total_entregas_concluidas = sum([len(r.get('entregas', [])) for r in historico_geral])

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("📦 Pedidos no Galpão", total_pedidos_galpao, help="Aguardando embarque")
    col_m2.metric("🚚 Prontos no Veículo", total_pedidos_caminhao, help="Embarcados para rota")
    col_m3.metric("🛣️ Rotas Concluídas", total_rotas_realizadas, help="Últimas 48 horas")
    col_m4.metric("📍 Entregas Realizadas", total_entregas_concluidas, help="Total de pontos atendidos")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- INTELIGÊNCIA GEOGRÁFICA ---
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

    # --- MENU LATERAL DO LOGUII ---
    st.sidebar.header("🔍 1. Adicionar à Fila")
    if status_ok and not df_clientes.empty:
        colunas_necessarias = ['Código', 'Cliente', 'Endereco', 'Numero']
        if all(col in df_clientes.columns for col in colunas_necessarias):
            opcoes = df_clientes['Código'] + " - " + df_clientes['Cliente']
            cliente_selecionado = st.sidebar.selectbox("Digite o Código ou Nome do Cliente:", options=["Selecione..."] + opcoes.tolist())
            if st.sidebar.button("➕ Enviar para Galpão", type="primary"):
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
                            "status": "espera", "itens": [],
                            "lat": float(lat) if lat else None, 
                            "lon": float(lon) if lon else None
                        })
                        salvar_pendentes(st.session_state.pendentes)
                        st.sidebar.success(f"{dados_cli['Cliente']} adicionado ao Galpão!")
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
            "status": "espera", "itens": [],
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
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()

    # --- LISTAGEM DE PENDENTES E MAPA PYDECK ---
    st.subheader("🗺️ Visão Geográfica Geral")
    st.markdown("Legenda: 🔵 **Base** | 🟢 **No Veículo (Embarcados)** | 🔴 **No Galpão (Espera)**")

    for p in st.session_state.pendentes:
        if not p.get('lat') or not p.get('lon'):
            lat, lon = geocodificar(p['endereco'])
            if lat and lon:
                p['lat'], p['lon'] = float(lat), float(lon)

    lat_base, lon_base = geocodificar("Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP, Brasil")

    if st.session_state.pendentes or (lat_base and lon_base):
        dados_mapa_espera = []
        dados_mapa_rota = []
        
        for p in st.session_state.pendentes:
            if p.get('lat') and p.get('lon'):
                nome_tratado = remover_acentos(p.get("cliente", "Desconhecido"))
                if len(nome_tratado) > 40:
                    nome_tratado = nome_tratado[:37] + "..."
                
                ponto = {
                    "lat": float(p['lat']), 
                    "lon": float(p['lon']),
                    "Cliente": nome_tratado,
                    "Endereco": p.get("endereco", "Não informado")
                }
                if p.get('status', 'espera') == 'rota':
                    dados_mapa_rota.append(ponto)
                else:
                    dados_mapa_espera.append(ponto)
        
        dados_mapa_base = []
        if lat_base and lon_base:
            dados_mapa_base.append({
                "lat": lat_base,
                "lon": lon_base,
                "Cliente": "Base Uniao Embalagens",
                "Endereco": "Ponto de Partida e Retorno"
            })

        df_espera_mapa = pd.DataFrame(dados_mapa_espera) if dados_mapa_espera else pd.DataFrame(columns=["lat", "lon", "Cliente", "Endereco"])
        df_rota_mapa = pd.DataFrame(dados_mapa_rota) if dados_mapa_rota else pd.DataFrame(columns=["lat", "lon", "Cliente", "Endereco"])
        df_base_mapa = pd.DataFrame(dados_mapa_base)

        with st.expander("📍 Expandir Mapa Interativo", expanded=True):
            camadas = []
            
            if not df_espera_mapa.empty:
                camadas.append(pdk.Layer(
                    'ScatterplotLayer', data=df_espera_mapa, get_position='[lon, lat]',
                    get_color='[200, 30, 0, 180]', get_radius=150, pickable=True
                ))
                camadas.append(pdk.Layer(
                    'TextLayer', data=df_espera_mapa, get_position='[lon, lat]',
                    get_text='Cliente', get_color='[255, 255, 255, 255]', get_size=11,
                    get_alignment_baseline="'bottom'", get_pixel_offset=[0, -15],
                    background=True, get_background_color='[0, 0, 0, 150]'
                ))
            
            if not df_rota_mapa.empty:
                camadas.append(pdk.Layer(
                    'ScatterplotLayer', data=df_rota_mapa, get_position='[lon, lat]',
                    get_color='[30, 200, 50, 200]', get_radius=180, pickable=True
                ))
                camadas.append(pdk.Layer(
                    'TextLayer', data=df_rota_mapa, get_position='[lon, lat]',
                    get_text='Cliente', get_color='[255, 255, 255, 255]', get_size=11, 
                    get_alignment_baseline="'bottom'", get_pixel_offset=[0, -18],
                    background=True, get_background_color='[0, 0, 0, 150]'
                ))

            if not df_base_mapa.empty:
                camadas.append(pdk.Layer(
                    'ScatterplotLayer', data=df_base_mapa, get_position='[lon, lat]',
                    get_color='[30, 100, 240, 220]', get_radius=220, pickable=True
                ))
                camadas.append(pdk.Layer(
                    'TextLayer', data=df_base_mapa, get_position='[lon, lat]',
                    get_text='Cliente', get_color='[255, 255, 255, 255]', get_size=12, 
                    get_alignment_baseline="'bottom'", get_pixel_offset=[0, -22],
                    background=True, get_background_color='[0, 0, 0, 180]'
                ))

            lat_centro = lat_base if lat_base else (-20.5387)
            lon_centro = lon_base if lon_base else (-47.4005)

            view_state = pdk.ViewState(latitude=lat_centro, longitude=lon_centro, zoom=13, pitch=0)
            r = pdk.Deck(map_style=None, layers=camadas, initial_view_state=view_state, tooltip={"text": "{Cliente}\n{Endereco}"})
            st.pydeck_chart(r)

    st.divider()

    # FUNÇÃO REUTILIZÁVEL PARA DESENHAR LINHAS DE PEDIDO
    def renderizar_linha_pedido(i, p, is_embarcado):
        acao_label = "⬇️ Retirar" if is_embarcado else "⬆️ Embarcar"
        
        with st.container(border=True):
            col_btn, col_cli, col_end, col_ped, col_hor, col_bell, col_del = st.columns([1.5, 3, 3, 1.5, 1, 0.5, 0.5])
            
            if col_btn.button(acao_label, key=f"acao_{p['uid']}", type="primary" if not is_embarcado else "secondary", use_container_width=True):
                p['status'] = 'espera' if is_embarcado else 'rota'
                salvar_pendentes(st.session_state.pendentes)
                st.rerun()
                
            p['cliente'] = col_cli.text_input("Cliente:", value=p['cliente'], key=f"cli_{p['uid']}", label_visibility="collapsed")
            
            novo_endereco = col_end.text_input("Endereço:", value=p['endereco'], key=f"end_{p['uid']}", label_visibility="collapsed")
            if novo_endereco != p.get('endereco', ''):
                p['endereco'] = novo_endereco
                lat, lon = geocodificar(novo_endereco)
                p['lat'] = float(lat) if lat else None
                p['lon'] = float(lon) if lon else None
                salvar_pendentes(st.session_state.pendentes)
                st.rerun()

            if p.get('lat') is None:
                col_end.markdown("<span style='color:#d32f2f; font-size:12px; font-weight:bold;'>⚠️ Endereço não localizado no mapa. Rota ignorará este ponto.</span>", unsafe_allow_html=True)

            p['pedido_num'] = col_ped.text_input("Pedido:", value=p.get('pedido_num', ''), key=f"ped_{p['uid']}", label_visibility="collapsed", placeholder="Nº Ped.")
            
            if p.get('urgente', False):
                p['horario'] = col_hor.text_input("Horário:", value=p.get('horario', ''), key=f"hor_{p['uid']}", placeholder="14h", label_visibility="collapsed")
            else:
                col_hor.write("")

            btn_sino = "🔔" if p.get('urgente', False) else "🔕"
            if col_bell.button(btn_sino, key=f"urg_{p['uid']}", help="Marcar/Desmarcar Urgência"):
                p['urgente'] = not p.get('urgente', False)
                salvar_pendentes(st.session_state.pendentes)
                st.rerun()

            if col_del.button("🗑️", key=f"del_{p['uid']}"):
                st.session_state.pendentes.pop(i)
                salvar_pendentes(st.session_state.pendentes)
                st.rerun()
                
            p['itens'] = st.multiselect("📦 Itens do Pedido:", options=lista_estoque, default=p.get('itens', []), key=f"itens_{p['uid']}")

    # --- FILA 1: VEÍCULOS / EMBARCADOS ---
    st.markdown("### 🚚 Prontos para Embarque (Veículo)")
    st.markdown("Itens que **entrarão na próxima rota gerada**.")
    pedidos_rota = [(i, p) for i, p in enumerate(st.session_state.pendentes) if p.get('status', 'espera') == 'rota']
    
    if pedidos_rota:
        for i, p in pedidos_rota:
            renderizar_linha_pedido(i, p, True)
    else:
        st.info("Nenhum pedido no veículo. Selecione pedidos do Galpão abaixo para embarcar.")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- FILA 2: GALPÃO (ESPERA) ---
    st.markdown("### 📦 Galpão de Espera (Backlog)")
    st.markdown("Pedidos aguardando na base. **Não** entrarão na rota até serem embarcados.")
    pedidos_espera = [(i, p) for i, p in enumerate(st.session_state.pendentes) if p.get('status', 'espera') == 'espera']
    
    if pedidos_espera:
        for i, p in pedidos_espera:
            renderizar_linha_pedido(i, p, False)
    else:
        st.success("O galpão está vazio!")

    salvar_pendentes(st.session_state.pendentes)

    # --- ROTINAS DE IMPRESSÃO E MAPA ---
    def gerar_pdf(ordem_entregas, veiculo_selecionado, nome_motorista):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        largura, altura = A4
        if os.path.exists(caminho_logo):
            c.drawImage(caminho_logo, 40, altura - 80, width=120, height=45, preserveAspectRatio=True, mask='auto')
        
        c.setFont("Helvetica-Bold", 16)
        c.drawString(180, altura - 50, "LoGuii Solução Logística")
        c.setFont("Helvetica", 10)
        c.drawString(180, altura - 65, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        c.setFont("Helvetica-Bold", 11)
        c.drawString(180, altura - 82, f"Veículo: {veiculo_selecionado}")
        if nome_motorista:
            c.drawString(180, altura - 98, f"Motorista: {nome_motorista}")
            y_offset = 125
        else:
            y_offset = 115
            
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, altura - y_offset, "Ponto de Partida:")
        c.setFont("Helvetica", 12)
        c.drawString(50, altura - (y_offset + 15), "Rua Doutor Ivom Rodrigues Pereira, 5078")
        c.line(50, altura - (y_offset + 30), largura - 50, altura - (y_offset + 30))
        
        y = altura - (y_offset + 60)
        
        for idx, p in enumerate(ordem_entregas):
            if y < 100:
                c.showPage()
                y = altura - 50
                
            prefixo = f"[URGENTE {p.get('horario', '')}] " if p.get('urgente') else ""
            num_pedido_str = f" | Pedido: {p.get('pedido_num')}" if p.get('pedido_num') else ""
            
            if p.get('urgente'):
                c.setFillColorRGB(0.8, 0, 0)
                
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, f"[{idx+1}] {prefixo}Cliente: {p['cliente']}{num_pedido_str}")
            c.setFillColorRGB(0, 0, 0) 
            c.rect(largura - 70, y - 10, 15, 15)
            y -= 15
            
            c.setFont("Helvetica", 11)
            c.drawString(50, y, f"Endereço: {p['endereco']}")
            y -= 15
            
            if p.get('itens'):
                y -= 5
                c.setFont("Helvetica-Bold", 10)
                c.drawString(50, y, "Itens a Carregar:")
                y -= 15
                c.setFont("Helvetica", 10)
                for item in p['itens']:
                    if y < 50:
                        c.showPage()
                        y = altura - 50
                    c.rect(50, y, 10, 10) 
                    c.drawString(65, y + 2, item[:85] + "..." if len(item) > 85 else item)
                    y -= 15
            y -= 5
            c.line(50, y, largura - 50, y)
            y -= 25
            
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "📍 RETORNO: Base União Embalagens")
        y -= 15
        c.setFont("Helvetica", 11)
        c.drawString(50, y, "Endereço: Rua Doutor Ivom Rodrigues Pereira, 5078")
        c.save()
        buffer.seek(0)
        return buffer

    def extrair_minutos(horario_str):
        if not horario_str: return 720
        try:
            numeros = re.findall(r'\d+', str(horario_str))
            if len(numeros) >= 2: return int(numeros[0]) * 60 + int(numeros[1])
            elif len(numeros) == 1:
                n = numeros[0]
                if len(n) >= 3: return int(n[:-2]) * 60 + int(n[-2:])
                return int(n) * 60
        except: pass
        return 720

    def otimizar_rota_com_urgencia(origem_lat, origem_lon, pedidos):
        if not pedidos: return []
        
        unvisited = pedidos.copy()
        current_lat, current_lon = float(origem_lat), float(origem_lon)
        rota_ordenada = []
        
        while unvisited:
            best_score = float('inf')
            best_idx = -1
            for i, p in enumerate(unvisited):
                dist = haversine(current_lat, current_lon, float(p['lat']), float(p['lon']))
                bonus = 8 if p.get('urgente') else 0 
                score = dist - bonus
                if score < best_score:
                    best_score = score
                    best_idx = i
            next_p = unvisited.pop(best_idx)
            rota_ordenada.append(next_p)
            current_lat, current_lon = float(next_p['lat']), float(next_p['lon'])
            
        melhoria = True
        iteracoes = 0
        while melhoria and iteracoes < 100:
            melhoria = False
            iteracoes += 1
            for i in range(len(rota_ordenada) - 1):
                for j in range(i + 1, len(rota_ordenada)):
                    if j - i == 1: continue
                    
                    lat_prev = float(rota_ordenada[i-1]['lat']) if i > 0 else float(origem_lat)
                    lon_prev = float(rota_ordenada[i-1]['lon']) if i > 0 else float(origem_lon)
                    
                    lat_i, lon_i = float(rota_ordenada[i]['lat']), float(rota_ordenada[i]['lon'])
                    lat_j, lon_j = float(rota_ordenada[j]['lat']), float(rota_ordenada[j]['lon'])
                    
                    lat_next = float(rota_ordenada[j+1]['lat']) if j+1 < len(rota_ordenada) else float(origem_lat)
                    lon_next = float(rota_ordenada[j+1]['lon']) if j+1 < len(rota_ordenada) else float(origem_lon)
                    
                    dist_atual = haversine(lat_prev, lon_prev, lat_i, lon_i) + \
                                 haversine(lat_j, lon_j, lat_next, lon_next)
                    
                    dist_nova = haversine(lat_prev, lon_prev, lat_j, lon_j) + \
                                haversine(lat_i, lon_i, lat_next, lon_next)
                                
                    if dist_nova < dist_atual - 0.05:
                        rota_ordenada[i:j+1] = list(reversed(rota_ordenada[i:j+1]))
                        melhoria = True
                        
        return rota_ordenada

    # --- OTIMIZAÇÃO, GESTÃO DE VEÍCULOS E GERAÇÃO DA ROTA ---
    st.divider()
    st.subheader("🗺️ Geração da Rota, Veículos & Impressão")
    
    col_veiculo_sel, col_mot_sel = st.columns(2)
    with col_veiculo_sel:
        veiculo_escolhido = st.selectbox("🚗 Selecione o Veículo Responsável:", options=FROTA_UNIAO)
    with col_mot_sel:
        nome_motorista = st.text_input("👨‍✈️ Nome do Motorista (Opcional):", placeholder="Ex: Roberto")
    
    pedidos_prontos = [p for p in st.session_state.pendentes if p.get('status', 'espera') == 'rota']

    if st.button("🗺️ Gerar Rota para o Veículo", type="primary"):
        if not pedidos_prontos:
            st.warning("O veículo está vazio! Embarque pelo menos um pedido no Galpão para gerar a rota.")
        else:
            with st.spinner("Otimizando rota com algoritmo avançado para evitar cruzamentos..."):
                lat_o, lon_o = geocodificar("Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP, Brasil")
                if not (lat_o and lon_o):
                    st.error("Erro ao localizar endereço base.")
                else:
                    enderecos_validos = [p for p in pedidos_prontos if p.get('lat') and p.get('lon')]
                    if enderecos_validos:
                        ordem_entregas = otimizar_rota_com_urgencia(lat_o, lon_o, enderecos_validos)
                        st.success(f"Rota perfeita gerada para o veículo **{veiculo_escolhido}** com sucesso!")
                        st.subheader("📍 Ordem Sugerida de Entregas")
                        
                        for idx, p in enumerate(ordem_entregas):
                            urg_text = f" **[URG. {p.get('horario', '')}]** " if p.get('urgente') else ""
                            st.markdown(f"**Parada {idx+1}:** {urg_text}{p['cliente']} — *{p['endereco']}*")
                        
                        origem_link = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP".replace(" ", "+")
                        pontos = "|".join([f"{p['endereco']}, Franca, SP".replace(" ", "+") for p in ordem_entregas])
                        link_maps = f"https://www.google.com/maps/dir/?api=1&origin={origem_link}&destination={origem_link}&waypoints={pontos}"
                        
                        st.markdown(f"[🔗 Abrir Rota no Google Maps]({link_maps})", unsafe_allow_html=True)
                        
                        st.divider()
                        pdf_arquivo = gerar_pdf(ordem_entregas, veiculo_escolhido, nome_motorista)
                        nome_arquivo = f"LoGuii_{veiculo_escolhido.replace(' ', '_')}_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf"
                        
                        st.download_button(
                            label="📄 Baixar PDF com Checklist da Rota", 
                            data=pdf_arquivo, 
                            file_name=nome_arquivo, 
                            mime="application/pdf", 
                            type="primary",
                            on_click=lambda: (
                                st.session_state.update({"pendentes": [p for p in st.session_state.pendentes if p.get('status', 'espera') != 'rota']}),
                                salvar_pendentes(st.session_state.pendentes)
                            )
                        )
                        
                        historico = carregar_historico()
                        historico = [r for r in historico if (time.time() - r.get("timestamp", 0)) <= 172800]
                        
                        historico.insert(0, {
                            "timestamp": time.time(), 
                            "data_formatada": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                            "veiculo": veiculo_escolhido,
                            "motorista": nome_motorista or "Não informado", 
                            "entregas": ordem_entregas, 
                            "link_maps": link_maps,
                            "link_rastreamento": "" 
                        })
                        salvar_historico(historico)
                    else:
                        st.error("Não foram encontrados endereços válidos para criar a rota.")

    # --- HISTÓRICO DE ROTAS E RASTREAMENTO AO VIVO (COM IFRAME INTEGRADO) ---
    st.divider()
    st.subheader("🕒 Histórico de Rotas, Veículos e Rastreamento (Últimas 48h)")
    
    hist = carregar_historico()
    hist = [r for r in hist if (time.time() - r.get("timestamp", 0)) <= 172800]

    if hist:
        for i, rota in enumerate(hist):
            veiculo_reg = rota.get('veiculo', 'Veículo Geral')
            motorista_reg = rota.get('motorista', 'Não informado')
            with st.expander(f"🚗 [{veiculo_reg}] Rota de {rota['data_formatada']} - Motorista: {motorista_reg} ({len(rota['entregas'])} entregas)"):
                
                st.markdown("---")
                st.markdown("### 📡 Visualização de Rastreamento ao Vivo")
                st.markdown("Cole o link de compartilhamento do Google Maps ou o código de incorporação (`iframe`) abaixo para visualizar a rota em tempo real direto na tela:")
                
                link_atual = rota.get('link_rastreamento', '')
                novo_link = st.text_input("Link de Rastreamento ao Vivo:", value=link_atual, key=f"link_rastreio_{i}", placeholder="Ex: https://www.google.com/maps/embed?pb=... ou link de compartilhamento")
                
                if novo_link != link_atual:
                    hist[i]['link_rastreamento'] = novo_link
                    salvar_historico(hist)
                    st.rerun()
                
                if novo_link:
                    if "<iframe" in novo_link:
                        components.html(novo_link, height=400)
                    else:
                        safe_url = novo_link.replace("&output=embed", "") + "&output=embed" if "output=embed" not in novo_link else novo_link
                        components.html(f'<iframe src="{safe_url}" width="100%" height="400" style="border:0;" allowfullscreen="" loading="lazy"></iframe>', height=400)
                
                st.markdown("---")
                st.markdown(f"[🔗 Abrir Rota Completa no Google Maps]({rota['link_maps']})", unsafe_allow_html=True)
                
                for p in rota['entregas']:
                    urg_text = f" **[URG. {p.get('horario', '')}]**" if p.get('urgente') else ""
                    st.write(f"-{urg_text} {p['cliente']}: *{p['endereco']}*")
                    
                    if p.get('itens'):
                        for item in p['itens']:
                            st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;📦 {item}")
                
                col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
                with col_b1:
                    st.download_button(label="📄 Re-imprimir PDF", data=gerar_pdf(rota['entregas'], veiculo_reg, motorista_reg), file_name=f"LoGuii_Hist_{i}.pdf", mime="application/pdf", key=f"dl_hist_{i}")
                with col_b2:
                    if st.button("✏️ Devolver para o Galpão", key=f"edit_hist_{i}"):
                        for p_hist in rota['entregas']:
                            p_hist['uid'] = f"hist_{time.time()}_{p_hist['cliente']}"
                            p_hist['status'] = 'espera' 
                            st.session_state.pendentes.append(p_hist)
                        salvar_pendentes(st.session_state.pendentes)
                        hist.pop(i)
                        salvar_historico(hist)
                        st.rerun()
                with col_b3:
                    if st.button("🗑️ Excluir Rota", key=f"del_hist_{i}", type="secondary"):
                        hist.pop(i)
                        salvar_historico(hist)
                        st.rerun()
    else:
        st.info("Nenhuma rota salva ainda.")
